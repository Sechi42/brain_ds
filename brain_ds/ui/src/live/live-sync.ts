const NOOP = () => {};

const eventToMessage = (event) => {
  try {
    if (typeof event?.data === 'string') return JSON.parse(event.data);
  } catch {
    return null;
  }
  return event?.data && typeof event.data === 'object' ? event.data : null;
};

export class LiveDataStore {
  constructor(initialContext, nodesDataSet, edgesDataSet) {
    this.context = initialContext || {};
    this.nodesDataSet = nodesDataSet;
    this.edgesDataSet = edgesDataSet;
    this.onNodeAdded = NOOP;
    this.onNodeRemoved = NOOP;
    this.onEventBuffered = NOOP;
    this.onReceipt = NOOP;
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

  seedFromContext(context) {
    const nodes = Array.isArray(context?.nodes) ? context.nodes : [];
    const edges = Array.isArray(context?.edges) ? context.edges : [];
    this.nodeMap.clear();
    this.edgeMap.clear();
    for (const node of nodes) {
      this.nodeMap.set(String(node.id), { ...node });
    }
    for (const edge of edges) {
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
      const edge = { ...payload };
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
    const selector = `.d4-node[data-id="${String(nodeId)}"], .graph-node[data-id="${String(nodeId)}"]`;
    const el = document.querySelector(selector);
    if (!el) return;
    this._armHighlight(el, kind);
  }

  _setEdgeHighlight(edge, kind) {
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
      fetch(`/api/graphs/${encoded}/nodes`),
      fetch(`/api/graphs/${encoded}/edges`),
    ]);
    const nodes = await nodesResp.json();
    const edges = await edgesResp.json();
    this.context.nodes = Array.isArray(nodes) ? nodes : [];
    this.context.edges = Array.isArray(edges) ? edges : [];
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
    });
    socket.addEventListener('message', (evt) => {
      const parsed = eventToMessage(evt);
      if (parsed) store.queueOrApply(parsed);
    });
    socket.addEventListener('close', scheduleReconnect);
    socket.addEventListener('error', () => {
      socket?.close();
    });
  };

  connect();
  return () => {
    socket?.close();
  };
}
