const NOOP = () => {};

const eventToMessage = (event) => {
  try {
    if (typeof event?.data === 'string') return JSON.parse(event.data);
  } catch {
    return null;
  }
  return event?.data && typeof event.data === 'object' ? event.data : null;
};

// ── Presence model types (design contract — JSDoc only; file eval'd as plain JS) ──

/**
 * @typedef {Object} AgentPresence
 * @property {string} agentId
 * @property {string} label
 * @property {string} role    — Agent role as reported by the transport (e.g. 'orchestrator', 'apply', 'verify'); defaults to 'agent' if not supplied.
 * @property {'active'|'idle'|'error'} status
 * @property {string} lastSeen
 * @property {string[]} recentTools
 *
 * AgentPresence — one entry per distinct agent seen in this session.
 * Populated from `tool.invoked` event payloads; never cleared on disconnect.
 */

/**
 * @typedef {Object} ActivityEntry
 * @property {string} agentId
 * @property {string} tool
 * @property {string} timestamp
 * @property {string} status
 *
 * ActivityEntry — one item in the recentActivity ring buffer (cap 200).
 * Pushed on every `tool.invoked` event; never dropped.
 */

/** Rate-limit for panel update notifications: ≤4 Hz = 250 ms. */
const PRESENCE_THROTTLE_MS = 250;

/** Maximum entries in the recentActivity ring buffer. */
const ACTIVITY_RING_CAP = 200;

export class LiveDataStore {
  constructor(initialContext, nodesDataSet, edgesDataSet) {
    this.context = initialContext || {};
    this.nodesDataSet = nodesDataSet;
    this.edgesDataSet = edgesDataSet;
    this.onNodeAdded = NOOP;
    this.onNodeRemoved = NOOP;
    this.onEventBuffered = NOOP;
    this.onReceipt = NOOP;
    // ── Presence model (T2.2 / T2.4) ─────────────────────────────────────────
    /** Known agents. Never cleared on disconnect — survives transport loss. @type {Map<string, AgentPresence>} */
    this.presenceByAgent = new Map();
    /** Activity ring buffer: all tool.invoked events, capped at ACTIVITY_RING_CAP. @type {ActivityEntry[]} */
    this.recentActivity = [];
    /** Transport state: 'connected' | 'reconnecting'. */
    this.connectionState = 'connected';
    /** Called whenever connectionState changes. */
    this.onConnectionStateChange = NOOP;
    /** Presence-update subscribers (notified at ≤4 Hz). @type {Array<()=>void>} */
    this._presenceSubscribers = [];
    /** Throttle timer handle for presence panel notifications. */
    this._presenceUpdateTimer = null;
    // ─────────────────────────────────────────────────────────────────────────
    this.bufferQueue = [];
    this.isFetchComplete = false;
    this.nodeMap = new Map();
    this.edgeMap = new Map();
    this.adjacency = new Map();
    this.detailIndex = { ...(this.context.detail_index || {}) };
    this.pendingPlacement = new Set();
    this.highlightTimers = new Map();
    this.seedFromContext(this.context);
  }

  // ── Presence model public API (T2.2) ─────────────────────────────────────────

  /** Return the presenceByAgent Map. @returns {Map<string, AgentPresence>} */
  getPresence() {
    return this.presenceByAgent;
  }

  /**
   * Subscribe to presence updates. cb is called at ≤4 Hz when the model changes.
   * @param {()=>void} cb
   * @returns {()=>void} unsubscribe function
   */
  subscribePresence(cb) {
    this._presenceSubscribers.push(cb);
    return () => {
      this._presenceSubscribers = this._presenceSubscribers.filter((s) => s !== cb);
    };
  }

  /** Schedule a throttled notification to presence subscribers (≤4 Hz). */
  _notifyPresence() {
    if (this._presenceUpdateTimer !== null) return; // already scheduled
    this._presenceUpdateTimer = setTimeout(() => {
      this._presenceUpdateTimer = null;
      for (const cb of this._presenceSubscribers) {
        try { cb(); } catch { /* subscriber errors must not propagate */ }
      }
    }, PRESENCE_THROTTLE_MS);
  }

  /** Update presenceByAgent from a tool.invoked payload. @param {Record<string,unknown>} payload */
  _applyPresence(payload) {
    const agentId = String(payload?.agent_id || payload?.tool || 'unknown');
    const tool = String(payload?.tool || '');
    const timestamp = String(payload?.timestamp || new Date().toISOString());
    const status = String(payload?.status || 'ok').toLowerCase() === 'error' ? 'error' : 'active';
    // W2: role from transport payload; default to 'agent' if not provided
    const role = String(payload?.role || 'agent');

    // Always push to activity log — never dropped
    const entry = { agentId, tool, timestamp, status };
    this.recentActivity.push(entry);
    // Enforce ring cap (200 entries max)
    if (this.recentActivity.length > ACTIVITY_RING_CAP) {
      this.recentActivity.splice(0, this.recentActivity.length - ACTIVITY_RING_CAP);
    }

    // Update presence record
    const existing = this.presenceByAgent.get(agentId);
    const recentTools = existing?.recentTools ?? [];
    if (tool && !recentTools.includes(tool)) {
      recentTools.unshift(tool);
      if (recentTools.length > 5) recentTools.length = 5;
    }
    const updated = {
      agentId,
      label: agentId,
      role,
      status,
      lastSeen: timestamp,
      recentTools,
    };
    this.presenceByAgent.set(agentId, updated);

    // Throttle panel DOM notification (≤4 Hz) — the state update above is immediate
    this._notifyPresence();
  }

  // The REST API (/api/edges) emits {edge_id, source, target}; the viewer contract
  // (render_context, D4 paint loop, edgeId, rebuildAdjacency) uses {from, to}.
  // Normalize every edge that enters the store so reseeded edges are not dropped.
  normalizeEdge(edge) {
    const e = { ...edge };
    if (e.from === undefined && e.source !== undefined) e.from = e.source;
    if (e.to === undefined && e.target !== undefined) e.to = e.target;
    if (e.id === undefined && e.edge_id !== undefined) e.id = e.edge_id;
    return e;
  }

  seedFromContext(context) {
    const nodes = Array.isArray(context?.nodes) ? context.nodes : [];
    const edges = Array.isArray(context?.edges) ? context.edges : [];
    this.nodeMap.clear();
    this.edgeMap.clear();
    for (const node of nodes) {
      this.nodeMap.set(String(node.id), { ...node });
    }
    for (const rawEdge of edges) {
      const edge = this.normalizeEdge(rawEdge);
      const id = this.edgeId(edge);
      this.edgeMap.set(id, { ...edge, id });
    }
    this.rebuildAdjacency();
  }

  edgeId(edge) {
    if (edge?.id !== undefined && edge?.id !== null) return String(edge.id);
    return `${String(edge?.from)}->${String(edge?.to)}:${String(edge?.label || '')}`;
  }

  rebuildAdjacency() {
    this.adjacency.clear();
    for (const edge of this.edgeMap.values()) {
      const from = String(edge.from);
      const to = String(edge.to);
      if (!this.adjacency.has(from)) this.adjacency.set(from, new Set());
      if (!this.adjacency.has(to)) this.adjacency.set(to, new Set());
      this.adjacency.get(from).add(to);
      this.adjacency.get(to).add(from);
    }
  }

  getNodes() {
    return Array.from(this.nodeMap.values());
  }

  getEdges() {
    return Array.from(this.edgeMap.values());
  }

  getAdjacency() {
    return this.adjacency;
  }

  getDetailIndex() {
    return this.detailIndex;
  }

  /**
   * seedPlacement(nodeId) — attempt to place a pending node at the centroid of its
   * positioned neighbors. Called from the RAF retry loop in the template.
   *
   * Returns true and removes nodeId from pendingPlacement if at least one neighbor
   * has a finite position in nodesDataSet (vis.js physics x/y).
   * Returns false and leaves nodeId in pendingPlacement when no positioned neighbor
   * is available yet (edges may not have arrived, or neighbors have no physics pos).
   */
  seedPlacement(nodeId) {
    const neighbors = this.adjacency.get(String(nodeId));
    if (!neighbors || neighbors.size === 0) return false;
    const positioned = [];
    for (const neighborId of neighbors) {
      const neighbor = this.nodesDataSet && typeof this.nodesDataSet.get === 'function'
        ? this.nodesDataSet.get().find((n) => String(n.id) === String(neighborId))
        : null;
      if (neighbor && isFinite(Number(neighbor.x)) && isFinite(Number(neighbor.y))) {
        positioned.push({ x: Number(neighbor.x), y: Number(neighbor.y) });
      }
    }
    if (positioned.length === 0) return false;
    const x = positioned.reduce((sum, p) => sum + p.x, 0) / positioned.length;
    const y = positioned.reduce((sum, p) => sum + p.y, 0) / positioned.length;
    if (this.nodesDataSet && typeof this.nodesDataSet.update === 'function') {
      this.nodesDataSet.update([{ id: nodeId, x, y }]);
    }
    this.pendingPlacement.delete(String(nodeId));
    return true;
  }

  applyEvent(event) {
    const name = String(event?.event || '');
    const payload = event?.payload || {};
    if (name === 'tool.invoked') {
      this._applyPresence(payload);
      this.renderReceipt(payload);
      this.onReceipt(payload);
      return;
    }
    if (name === 'node.updated' && this._shouldPreserveUnsavedEdits(payload)) {
      this._setConflictStale();
      return;
    }
    if (name === 'node.created' || name === 'node.updated') {
      const node = { ...payload };
      const id = String(node.id);
      const existed = this.nodeMap.has(id);
      this.nodeMap.set(id, node);
      this.nodesDataSet?.update?.([node]);
      if (!existed) {
        this.onNodeAdded(node);
        this.pendingPlacement.add(id);
      }
      this.context.nodes = this.getNodes();
      this.detailIndex[id] = {
        ...(this.detailIndex[id] || {}),
        node,
        sections: Array.isArray(node.card_sections) ? node.card_sections : (this.detailIndex[id]?.sections || []),
      };
      this._setNodeHighlight(id, event?.highlight_type || 'update');
      return;
    }
    if (name === 'node.deleted') {
      const nodeId = String(payload.id || payload.node_id);
      const existed = this.nodeMap.delete(nodeId);
      if (existed) {
        this.nodesDataSet?.remove?.([nodeId]);
        this.onNodeRemoved(nodeId);
      }
      this.pendingPlacement.delete(nodeId);
      this.context.nodes = this.getNodes();
      return;
    }
    if (name === 'edge.created' || name === 'edge.updated') {
      const edge = this.normalizeEdge(payload);
      const id = this.edgeId(edge);
      this.edgeMap.set(id, { ...edge, id });
      this.edgesDataSet?.update?.([{ ...edge, id }]);
      this.rebuildAdjacency();
      this.context.edges = this.getEdges();
      this._setEdgeHighlight(edge, event?.highlight_type || 'update');
      return;
    }
    if (name === 'edge.deleted') {
      const id = payload.id ? String(payload.id) : this.edgeId(payload);
      if (this.edgeMap.delete(id)) {
        this.edgesDataSet?.remove?.([id]);
      }
      this.rebuildAdjacency();
      this.context.edges = this.getEdges();
    }
  }

  renderReceipt(payload) {
    if (typeof document === 'undefined') return;
    const list = document.getElementById('ai-actions-receipts');
    if (!list) return;
    const item = document.createElement('li');
    const status = String(payload?.status || 'ok').toLowerCase() === 'error' ? 'error' : 'ok';
    const summary = String(payload?.params_summary || '').trim();
    const tool = String(payload?.tool || 'tool');
    const targetId = payload?.target_id ? String(payload.target_id) : '';
    const timestamp = String(payload?.timestamp || '');
    item.className = status === 'error' ? 'receipt-error' : 'receipt-ok';
    item.tabIndex = 0;
    item.dataset.targetId = targetId;
    item.innerHTML = `<strong>${tool}</strong> · ${summary || 'sin detalles'}${timestamp ? ` · ${timestamp}` : ''}`;
    item.addEventListener('click', () => {
      if (targetId) this._setNodeHighlight(targetId, 'update');
      item.focus({ preventScroll: true });
    });
    list.insertBefore(item, list.firstChild);
    while (list.children.length > 50) {
      list.removeChild(list.lastChild);
    }
  }

  _setNodeHighlight(nodeId, kind) {
    if (typeof document === 'undefined') return;
    const selector = `.d4-node[data-id="${String(nodeId)}"], .graph-node[data-id="${String(nodeId)}"]`;
    const el = document.querySelector(selector);
    if (!el) return;
    this._armHighlight(el, kind);
  }

  _setEdgeHighlight(edge, kind) {
    if (typeof document === 'undefined') return;
    const source = String(edge?.from || edge?.source || '');
    const target = String(edge?.to || edge?.target || '');
    if (!source || !target) return;
    const selector = `.d4-edge[data-source="${source}"][data-target="${target}"]`;
    const el = document.querySelector(selector);
    if (!el) return;
    this._armHighlight(el, kind);
  }

  _armHighlight(el, kind) {
    const key = el;
    const previous = this.highlightTimers.get(key);
    if (previous) window.clearTimeout(previous);
    el.setAttribute('data-highlight', String(kind || 'update'));
    const timeoutId = window.setTimeout(() => {
      el.removeAttribute('data-highlight');
      this.highlightTimers.delete(key);
    }, 2000);
    this.highlightTimers.set(key, timeoutId);
  }

  _shouldPreserveUnsavedEdits(payload) {
    const api = window.brainDsUI && window.brainDsUI.detailPanel;
    if (!api) return false;
    const selected = typeof api.getSelectedNodeId === 'function' ? api.getSelectedNodeId() : null;
    const hasEdits = typeof api.getHasEdits === 'function' ? api.getHasEdits() : false;
    const editMode = typeof api.isEditMode === 'function' ? api.isEditMode() : false;
    return Boolean(editMode && hasEdits && selected && String(selected) === String(payload?.id || ''));
  }

  _setConflictStale() {
    const body = document.getElementById('detail-body');
    const parent = body && body.parentElement;
    if (parent) parent.setAttribute('data-conflict', 'stale'); // data-conflict="stale"
    const banner = document.getElementById('detail-conflict-banner'); // #detail-conflict-banner
    if (banner) banner.removeAttribute('hidden');
    const api = window.brainDsUI && window.brainDsUI.detailPanel;
    if (api && typeof api.markConflictStale === 'function') api.markConflictStale();
  }

  queueOrApply(event) {
    if (String(event?.event || '') === 'tool.invoked') {
      this.applyEvent(event);
      return;
    }
    if (!this.isFetchComplete) {
      this.bufferQueue.push(event);
      this.onEventBuffered(event);
      return;
    }
    this.applyEvent(event);
  }

  flushBufferedEvents() {
    while (this.bufferQueue.length > 0) {
      const event = this.bufferQueue.shift();
      this.applyEvent(event);
    }
  }

  async syncWithServer(graphId) {
    const encoded = encodeURIComponent(graphId);
    const [nodesResp, edgesResp] = await Promise.all([
      fetch(`/api/nodes?graph_id=${encoded}`),
      fetch(`/api/edges?graph_id=${encoded}`),
    ]);
    const nodesPayload = await nodesResp.json();
    const edgesPayload = await edgesResp.json();
    const nodes = Array.isArray(nodesPayload) ? nodesPayload : (nodesPayload?.nodes || []);
    const edges = Array.isArray(edgesPayload) ? edgesPayload : (edgesPayload?.edges || []);
    this.context.nodes = Array.isArray(nodes) ? nodes : [];
    this.context.edges = (Array.isArray(edges) ? edges : []).map((edge) => this.normalizeEdge(edge));
    this.seedFromContext(this.context);
    this.nodesDataSet?.clear?.();
    this.edgesDataSet?.clear?.();
    if (this.context.nodes.length) this.nodesDataSet?.add?.(this.context.nodes);
    if (this.context.edges.length) this.edgesDataSet?.add?.(this.context.edges.map((edge) => ({ ...edge, id: this.edgeId(edge) })));
    this.isFetchComplete = true;
    this.flushBufferedEvents();
  }
}

export function connectWebSocket(graphId, store) {
  let retries = 0;
  let socket = null;
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = `${scheme}://${window.location.host}/api/events?graph_id=${encodeURIComponent(graphId)}`;

  const scheduleReconnect = () => {
    const backoff = Math.min(5000, 250 * (2 ** retries));
    retries += 1;
    window.setTimeout(connect, backoff);
  };

  const connect = () => {
    socket = new WebSocket(wsUrl);
    socket.addEventListener('open', () => {
      retries = 0;
      // T2.4: restore connected state — presenceByAgent is intentionally NOT cleared
      store.connectionState = 'connected';
      store.onConnectionStateChange('connected');
    });
    socket.addEventListener('message', (evt) => {
      const parsed = eventToMessage(evt);
      if (parsed) store.queueOrApply(parsed);
    });
    socket.addEventListener('close', () => {
      // T2.4: signal reconnecting; presenceByAgent stays intact
      store.connectionState = 'reconnecting';
      store.onConnectionStateChange('reconnecting');
      scheduleReconnect();
    });
    socket.addEventListener('error', () => {
      socket?.close();
    });
  };

  connect();
  return () => {
    socket?.close();
  };
}
