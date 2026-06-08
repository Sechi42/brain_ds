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
    // Hover takes visual priority over selection: while hovering, the selected
    // node "turns off" and only the hovered node + its neighborhood light up.
    // Selection is preserved in state and restored visually on blur.
    if (state.hoveredNodeId) {
      if (state.hoveredNodeId === nodeId) return 'hover-target';
      if (related.has(nodeId)) return 'hover-related';
      return 'default';
    }
    if (state.selectedNodeIds.has(nodeId)) return 'selected-target';
    if (state.selectedNodeIds.size > 0 && related.has(nodeId)) return 'selected-related';
    return 'default';
  };

  const d4SyncContainerState = () => {
    const hasHover = Boolean(state.hoveredNodeId);
    // Suppress selection styling while hovering so hover fully dominates.
    const hasSelection = state.selectedNodeIds.size > 0 && !state.hoveredNodeId;
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
    pop.setAttribute('role', 'tooltip');
    pop.setAttribute('aria-label', 'Node details');
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
    const neighborsCount = d4Adjacency().get(nodeId)?.size ?? 0;
    const componentLabel = node.component_id !== null && node.component_id !== undefined ? String(node.component_id) : '—';
    pop.innerHTML = `<div class="hover-popover-title"><span class="hover-popover-dot" aria-hidden="true"></span><strong>${resolveNodeLabel(node)}</strong></div>
<dl class="hover-popover-grid">
  <dt>Score</dt><dd>${Number(node.score ?? 0).toFixed(2)}</dd>
  <dt>Vecinos</dt><dd>${neighborsCount}</dd>
  <dt>Cluster</dt><dd>WCC-${componentLabel}</dd>
  <dt>Tipo</dt><dd>${node.type ?? 'Node'}</dd>
</dl>
<small class="hover-popover-hint">Click para fijar selección</small>`;
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
          } else if (typeof network._selectNodeById === 'function') {
            network._selectNodeById(node.id);
          }
          d4RenderOverlay();
        });
        // Node drag. The canvas host is pointer-events:none in overlay mode, so the
        // canvas drag never fires — drive it from the overlay button. Dragging mutates
        // the live node position, pins it via network.dragNodeId (so neighbors re-settle
        // around it via the reheated simulation), and on drop marks it fixed so it stays.
        const elBtn = el as HTMLElement;
        let d4DragMoved = false;
        el.addEventListener('pointerdown', (downEv: PointerEvent) => {
          if (downEv.button !== undefined && downEv.button !== 0) return;
          const canvas = network && network.canvas;
          if (!canvas || typeof network._screenToWorld !== 'function') return;
          d4DragMoved = false;
          const startX = downEv.clientX;
          const startY = downEv.clientY;
          network.isDragging = true;
          network.dragNodeId = node.id;
          if (typeof elBtn.setPointerCapture === 'function') {
            try { elBtn.setPointerCapture(downEv.pointerId); } catch (err) { /* noop */ }
          }
          const findLiveNode = (): { x: number; y: number; vx?: number; vy?: number; fixed?: boolean } | null => {
            const all = (network.data && network.data.nodes && typeof network.data.nodes.get === 'function')
              ? network.data.nodes.get() : [];
            return all.find((nn: { id: string | number }) => String(nn.id) === String(node.id)) || null;
          };
          const onPointerMove = (moveEv: PointerEvent) => {
            if (Math.abs(moveEv.clientX - startX) + Math.abs(moveEv.clientY - startY) > 3) d4DragMoved = true;
            const rect = canvas.getBoundingClientRect();
            const world = network._screenToWorld(moveEv.clientX - rect.left, moveEv.clientY - rect.top);
            const live = findLiveNode();
            if (live) { live.x = world.x; live.y = world.y; live.vx = 0; live.vy = 0; }
            network.temperature = Math.max(Number(network.temperature) || 0, 0.6);
            if (typeof network._wake === 'function') network._wake();
            d4RenderOverlay();
          };
          const onPointerUp = () => {
            network.isDragging = false;
            network.dragNodeId = null;
            if (d4DragMoved) {
              const live = findLiveNode();
              if (live) live.fixed = true;
              const swallowClick = (clickEv: Event) => {
                clickEv.stopPropagation();
                clickEv.preventDefault();
                elBtn.removeEventListener('click', swallowClick, true);
              };
              elBtn.addEventListener('click', swallowClick, true);
              setTimeout(() => elBtn.removeEventListener('click', swallowClick, true), 60);
            }
            if (typeof elBtn.releasePointerCapture === 'function') {
              try { elBtn.releasePointerCapture(downEv.pointerId); } catch (err) { /* noop */ }
            }
            document.removeEventListener('pointermove', onPointerMove);
            document.removeEventListener('pointerup', onPointerUp);
            network.temperature = Math.max(Number(network.temperature) || 0, 0.25);
            if (typeof network._wake === 'function') network._wake();
          };
          document.addEventListener('pointermove', onPointerMove);
          document.addEventListener('pointerup', onPointerUp);
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
    const activeEdgeIds = new Set<string>();
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
      activeEdgeIds.add(edgeId);
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
      const sourceColor = d4ColorVars(fromNode);
      line.style.setProperty('--node-color', sourceColor.color);
      line.style.setProperty('--node-color-muted', sourceColor.muted);
      line.setAttribute('x1', String(fromPos.x));
      line.setAttribute('y1', String(fromPos.y));
      line.setAttribute('x2', String(toPos.x));
      line.setAttribute('y2', String(toPos.y));
      line.setAttribute('data-source', fromId);
      line.setAttribute('data-target', toId);
      // Hover dominates selection (mirrors d4StateForNode): while hovering, only
      // the hovered node's edges are related/emphasized; selection edges recede.
      const touchesHover = Boolean(state.hoveredNodeId) && (fromId === state.hoveredNodeId || toId === state.hoveredNodeId);
      const touchesSelection = state.selectedNodeIds.has(fromId) || state.selectedNodeIds.has(toId);
      let isRelated: boolean;
      if (!hasInteraction) {
        isRelated = true;
      } else if (state.hoveredNodeId) {
        isRelated = touchesHover;
      } else {
        isRelated = touchesSelection;
      }
      line.setAttribute('data-related', isRelated ? 'true' : 'false');
      if (state.hoveredNodeId) {
        if (touchesHover) line.setAttribute('data-emphasis', 'hover');
        else line.removeAttribute('data-emphasis');
      } else if (touchesSelection) {
        line.setAttribute('data-emphasis', 'selected');
      } else {
        line.removeAttribute('data-emphasis');
      }
    });

    Array.from(state.edgeEls.keys()).forEach((edgeId) => {
      if (activeEdgeIds.has(edgeId)) return;
      const line = state.edgeEls.get(edgeId);
      if (line && line.parentNode) line.parentNode.removeChild(line);
      state.edgeEls.delete(edgeId);
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
  const onEscapeDismiss = (event: KeyboardEvent) => { if (event.key === 'Escape') d4HidePopover(); };

  network.on('hoverNode', onHoverNode);
  network.on('blurNode', onBlurNode);
  network.on('selectNode', onSelectNode);
  network.on('deselectNode', onDeselectNode);
  document.addEventListener('keydown', onEscapeDismiss);
  d4RenderOverlay();
  d4PaintLoop();

  cleanup = () => {
    network.off?.('hoverNode', onHoverNode);
    network.off?.('blurNode', onBlurNode);
    network.off?.('selectNode', onSelectNode);
    network.off?.('deselectNode', onDeselectNode);
    document.removeEventListener('keydown', onEscapeDismiss);
  };
}

export function unmount() {
  if (cleanup) cleanup();
  cleanup = null;
}
