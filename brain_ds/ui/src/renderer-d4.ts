type D4Node = {
  id: string | number;
  label?: string;
  title?: string;
  name?: string;
  type?: string;
  score?: number;
  component_id?: number | string;
  color?: string | { dark?: string; background?: string; light?: string };
};

type D4Edge = { from: string | number; to: string | number };

type D4MountArgs = {
  container: HTMLElement;
  network: any;
  dataset: { get: () => D4Node[] };
  edgesDataset: { get: () => D4Edge[] };
  nodesRoot: HTMLElement;
  edgesRoot: SVGElement;
  enteringIds?: Set<string>;
  hiddenTypes?: Set<string>;
  onNodeActivate?: (nodeId: string) => void;
};

let cleanup: null | (() => void) = null;

const d4HexToRgb = (hex: string | null | undefined): string => {
  if (typeof hex !== 'string') return '59,130,246';
  const cleaned = hex.replace('#', '').trim();
  const full = cleaned.length === 3 ? cleaned.split('').map((c) => c + c).join('') : cleaned;
  const bigint = parseInt(full, 16);
  if (Number.isNaN(bigint)) return '59,130,246';
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `${r},${g},${b}`;
};

const resolveNodeLabel = (node: D4Node): string => {
  const raw = node.label ?? node.title ?? node.name ?? node.id;
  const text = raw === null || raw === undefined ? '' : String(raw).trim();
  return text || String(node.id);
};

const resolveNodeAriaLabel = (node: D4Node, fallbackId: string): string => {
  const label = resolveNodeLabel(node);
  const typeLabel = String(node.type || 'Node');
  const numericScore = Number(node.score);
  const scoreLabel = Number.isFinite(numericScore) ? numericScore.toFixed(2) : 'N/A';
  return `${label || fallbackId}, ${typeLabel}, score ${scoreLabel}`;
};

export function mount(args: D4MountArgs) {
  unmount();

  const { container, network, dataset, edgesDataset, nodesRoot, edgesRoot } = args;
  const hasRequiredMountPoints = Boolean(container && nodesRoot && edgesRoot);
  const hasDatasets = Boolean(dataset && typeof dataset.get === 'function' && edgesDataset && typeof edgesDataset.get === 'function');
  const hasNetworkEvents = Boolean(network && typeof network.on === 'function');
  if (!hasRequiredMountPoints || !hasDatasets || !hasNetworkEvents) {
    cleanup = null;
    return;
  }
  const enteringIds = args.enteringIds || new Set<string>();
  const hiddenTypes = args.hiddenTypes || new Set<string>();
  const onNodeActivate = args.onNodeActivate;
  const palette = ['#3b82f6', '#14b8a6', '#f59e0b', '#a855f7', '#ef4444', '#22c55e', '#06b6d4', '#eab308'];

  const state = {
    hoveredNodeId: null as string | null,
    selectedNodeIds: new Set<string>(),
    nodeEls: new Map<string, HTMLElement>(),
    edgeEls: new Map<string, SVGLineElement>(),
    popoverEl: null as HTMLElement | null,
  };

  const d4NodeId = (value: unknown) => (value === null || value === undefined ? '' : String(value));
  const d4NodeMap = () => new Map((dataset.get() || []).map((n) => [d4NodeId(n.id), n]));
  const d4Adjacency = () => {
    const map = new Map<string, Set<string>>();
    (edgesDataset.get() || []).forEach((e) => {
      const from = d4NodeId(e.from);
      const to = d4NodeId(e.to);
      if (!map.has(from)) map.set(from, new Set());
      if (!map.has(to)) map.set(to, new Set());
      map.get(from)?.add(to);
      map.get(to)?.add(from);
    });
    return map;
  };
  const d4RelatedFor = (focusId: string | null) => (focusId ? new Set(d4Adjacency().get(focusId) || []) : new Set<string>());
  const d4ColorVars = (node: D4Node) => {
    let hex: string | null = null;
    const cid = node && node.component_id;
    if (cid !== null && cid !== undefined && cid !== '') {
      const idx = Math.abs(Number(cid)) % palette.length;
      if (!Number.isNaN(idx)) hex = palette[idx];
    }
    if (!hex && node && node.color) {
      if (typeof node.color === 'string') hex = node.color;
      else hex = node.color.dark || node.color.background || node.color.light || null;
    }
    if (!hex) hex = palette[0];
    const rgb = d4HexToRgb(hex);
    return { color: hex, muted: `rgba(${rgb},0.25)` };
  };

  const d4StateForNode = (nodeId: string, related: Set<string>) => {
    if (state.selectedNodeIds.has(nodeId)) return 'selected-target';
    if (state.hoveredNodeId && state.hoveredNodeId === nodeId) return 'hover-target';
    if (state.selectedNodeIds.size > 0 && related.has(nodeId)) return 'selected-related';
    if (state.hoveredNodeId && related.has(nodeId)) return 'hover-related';
    return 'default';
  };

  const d4SyncContainerState = () => {
    const hasHover = Boolean(state.hoveredNodeId);
    const hasSelection = state.selectedNodeIds.size > 0;
    container.setAttribute('data-has-hover', hasHover ? 'true' : 'false');
    container.setAttribute('data-has-selection', hasSelection ? 'true' : 'false');
    container.classList.toggle('has-hover', hasHover);
    container.classList.toggle('has-selection', hasSelection);
  };

  const d4EnsurePopover = () => {
    if (state.popoverEl) return state.popoverEl;
    const pop = document.createElement('div');
    pop.className = 'vis-popover hover-popover';
    pop.setAttribute('aria-hidden', 'true');
    pop.style.position = 'absolute';
    pop.style.zIndex = '4';
    container.appendChild(pop);
    state.popoverEl = pop;
    return pop;
  };
  const d4HidePopover = () => {
    if (!state.popoverEl) return;
    state.popoverEl.setAttribute('aria-hidden', 'true');
    state.popoverEl.style.display = 'none';
  };
  const d4ShowPopover = (nodeId: string, x: number, y: number) => {
    const node = d4NodeMap().get(nodeId);
    if (!node) return;
    const pop = d4EnsurePopover();
    const color = d4ColorVars(node);
    pop.style.setProperty('--node-color', color.color);
    pop.style.setProperty('--node-color-muted', color.muted);
    pop.innerHTML = `<div class="hover-popover-title"><span class="hover-popover-dot"></span><strong>${resolveNodeLabel(node)}</strong></div>`;
    pop.style.left = `${x + 24}px`;
    pop.style.top = `${y - 14}px`;
    pop.style.display = 'block';
    pop.setAttribute('aria-hidden', 'false');
  };

  const d4WorldToScreen = (w: { x: number; y: number }) => {
    if (network && typeof network._worldToScreen === 'function') return network._worldToScreen(w.x, w.y);
    const vp = (network && network.viewport) || { scale: 1, tx: 0, ty: 0 };
    return { x: w.x * vp.scale + vp.tx, y: w.y * vp.scale + vp.ty };
  };
  const d4ReadPositions = () => {
    const out: Record<string, { x: number; y: number }> = {};
    const all = network?.data?.nodes?.get?.() || [];
    for (let i = 0; i < all.length; i += 1) {
      const n = all[i];
      if (!n) continue;
      out[n.id] = { x: Number(n.x) || 0, y: Number(n.y) || 0 };
    }
    return out;
  };

  const d4RenderOverlay = () => {
    const nodeRecords = (dataset.get() || []).filter((n) => !hiddenTypes.has(String(n.type || '')));
    const world = d4ReadPositions();
    const selectedPrimary = state.selectedNodeIds.values().next().value || null;
    const related = d4RelatedFor(state.hoveredNodeId || selectedPrimary);
    d4SyncContainerState();

    nodeRecords.forEach((node, idx) => {
      const id = d4NodeId(node.id);
      const pos = d4WorldToScreen(world[String(node.id)] || { x: 0, y: 0 });
      let el = state.nodeEls.get(id);
      if (!el) {
        el = document.createElement('button');
        el.type = 'button';
        el.className = 'graph-node d4-node';
        el.dataset.id = id;
        el.innerHTML = '<span class="node-circle"></span><span class="node-label"></span>';
        el.addEventListener('mouseenter', () => { state.hoveredNodeId = id; d4RenderOverlay(); });
        el.addEventListener('mouseleave', () => { state.hoveredNodeId = null; d4HidePopover(); d4RenderOverlay(); });
        el.addEventListener('click', () => {
          state.selectedNodeIds = new Set([id]);
          if (typeof onNodeActivate === 'function') {
            onNodeActivate(id);
          } else if (typeof network.selectNodes === 'function') {
            network.selectNodes([node.id]);
          } else if (typeof network._selectNodeById === 'function') {
            network._selectNodeById(node.id);
          }
          d4RenderOverlay();
        });
        nodesRoot.appendChild(el);
        state.nodeEls.set(id, el);
      }
      const color = d4ColorVars(node);
      el.dataset.state = d4StateForNode(id, related);
      el.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0) translate(-50%, -50%)`;
      el.style.setProperty('--node-color', color.color);
      el.style.setProperty('--node-color-muted', color.muted);
      el.setAttribute('aria-label', resolveNodeAriaLabel(node, id));
      el.tabIndex = idx === 0 ? 0 : -1;
      const label = el.querySelector('.node-label');
      if (label) label.textContent = resolveNodeLabel(node);
      if (state.hoveredNodeId === id) d4ShowPopover(id, pos.x, pos.y);
      if (enteringIds.has(id)) enteringIds.delete(id);
    });

    const nodesById = d4NodeMap();
    const hasInteraction = Boolean(state.hoveredNodeId) || state.selectedNodeIds.size > 0;
    (edgesDataset.get() || []).forEach((edge, index) => {
      const fromId = d4NodeId(edge.from);
      const toId = d4NodeId(edge.to);
      const fromNode = nodesById.get(fromId);
      const toNode = nodesById.get(toId);
      if (!fromNode || !toNode) return;
      const fromPos = d4WorldToScreen(world[String(fromNode.id)] || { x: 0, y: 0 });
      const toPos = d4WorldToScreen(world[String(toNode.id)] || { x: 0, y: 0 });
      const edgeId = String(index);
      let line = state.edgeEls.get(edgeId);
      if (!line) {
        const protocolSep = (typeof document !== 'undefined' && typeof document.baseURI === 'string' && document.baseURI.indexOf('://') > -1)
          ? '://'
          : String.fromCharCode(58, 47, 47);
        const svgNs = `http${protocolSep}www.w3.org/2000/svg`;
        line = document.createElementNS(svgNs, 'line') as SVGLineElement;
        line.classList.add('d4-edge');
        edgesRoot.appendChild(line);
        state.edgeEls.set(edgeId, line);
      }
      line.setAttribute('x1', String(fromPos.x));
      line.setAttribute('y1', String(fromPos.y));
      line.setAttribute('x2', String(toPos.x));
      line.setAttribute('y2', String(toPos.y));
      const isRelated = !hasInteraction
        ? true
        : (
          fromId === state.hoveredNodeId
          || toId === state.hoveredNodeId
          || state.selectedNodeIds.has(fromId)
          || state.selectedNodeIds.has(toId)
        );
      line.setAttribute('data-related', isRelated ? 'true' : 'false');
      if (state.selectedNodeIds.has(fromId) || state.selectedNodeIds.has(toId)) {
        line.setAttribute('data-emphasis', 'selected');
      } else if (state.hoveredNodeId && (fromId === state.hoveredNodeId || toId === state.hoveredNodeId)) {
        line.setAttribute('data-emphasis', 'hover');
      } else {
        line.removeAttribute('data-emphasis');
      }
    });
  };

  const d4PaintLoop = () => {
    d4RenderOverlay();
    if (typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(d4PaintLoop);
    }
  };

  const onHoverNode = (params: { node?: string | number }) => { state.hoveredNodeId = d4NodeId(params && params.node); d4RenderOverlay(); };
  const onBlurNode = () => { state.hoveredNodeId = null; d4HidePopover(); d4RenderOverlay(); };
  const onSelectNode = (params: { nodes?: Array<string | number> }) => { state.selectedNodeIds = new Set((params.nodes || []).map((id) => d4NodeId(id))); d4RenderOverlay(); };
  const onDeselectNode = () => { state.selectedNodeIds = new Set(); d4RenderOverlay(); };

  network.on('hoverNode', onHoverNode);
  network.on('blurNode', onBlurNode);
  network.on('selectNode', onSelectNode);
  network.on('deselectNode', onDeselectNode);
  d4RenderOverlay();
  d4PaintLoop();

  cleanup = () => {
    network.off?.('hoverNode', onHoverNode);
    network.off?.('blurNode', onBlurNode);
    network.off?.('selectNode', onSelectNode);
    network.off?.('deselectNode', onDeselectNode);
  };
}

export function unmount() {
  if (cleanup) cleanup();
  cleanup = null;
}
