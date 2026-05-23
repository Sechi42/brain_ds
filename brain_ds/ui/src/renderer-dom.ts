type DomDataset = {
  get: (id?: unknown) => unknown;
  _subscribe?: (handler: () => void) => (() => void) | void;
};

type GraphNode = {
  id: string | number;
  x?: number;
  y?: number;
  label?: string;
  type?: string;
  score?: number;
  group?: number;
};

type GraphEdge = {
  from?: string | number;
  to?: string | number;
  source?: string | number;
  target?: string | number;
};

export interface DomRendererDeps {
  network: unknown;
  dataset: DomDataset;
  edgesDataset?: DomDataset;
  nodesRoot: HTMLElement;
  edgesRoot: SVGSVGElement;
  container: HTMLElement;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
const STATE_DEFAULT = 'default';
const ARROW_KEYS = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
const COLOR_MUTED_BY_INDEX = [
  'rgba(59,130,246,0.25)',
  'rgba(16,185,129,0.25)',
  'rgba(245,158,11,0.25)',
  'rgba(239,68,68,0.25)',
  'rgba(139,92,246,0.25)',
  'rgba(6,182,212,0.25)',
  'rgba(236,72,153,0.25)',
  'rgba(34,197,94,0.25)',
  'rgba(168,85,247,0.25)',
  'rgba(249,115,22,0.25)',
  'rgba(14,165,233,0.25)',
  'rgba(244,114,182,0.25)',
];

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function toNodeId(value: unknown): string {
  return value == null ? '' : String(value);
}

function nodeColorVars(group: number): string {
  const idx = Math.abs(group) % 12;
  return `--node-color:var(--wcc-c${idx});--node-color-muted:${COLOR_MUTED_BY_INDEX[idx]};`;
}

export function mount(deps: DomRendererDeps): { unmount(): void } {
  const getHoverId = (): string => {
    const value = (deps.network as { hoveredNodeId?: unknown } | undefined)?.hoveredNodeId;
    return toNodeId(value);
  };

  const getSelectionIds = (): Set<string> => {
    const raw = (deps.network as { selectedNodeIds?: unknown } | undefined)?.selectedNodeIds;
    return new Set(asArray<unknown>(raw).map((id) => toNodeId(id)).filter(Boolean));
  };

  const getEdgeEndpoints = (edge: GraphEdge): [string, string] => {
    return [toNodeId(edge.from ?? edge.source), toNodeId(edge.to ?? edge.target)];
  };

  const getRelatedNodes = (focusId: string): Set<string> => {
    if (!focusId || !deps.edgesDataset) return new Set<string>();
    const related = new Set<string>();
    const edges = asArray<GraphEdge>(deps.edgesDataset.get());
    for (const edge of edges) {
      const [fromId, toId] = getEdgeEndpoints(edge);
      if (fromId === focusId && toId) related.add(toId);
      if (toId === focusId && fromId) related.add(fromId);
    }
    return related;
  };

  const computeState = (nodeId: string, hoverId: string, selected: Set<string>, related: Set<string>): string => {
    if (selected.has(nodeId)) return 'selected-target';
    if (hoverId && nodeId === hoverId) return 'hover-target';
    if (selected.size > 0 && related.has(nodeId)) return 'selected-related';
    if (hoverId && related.has(nodeId)) return 'hover-related';
    return STATE_DEFAULT;
  };

  const renderAll = (): void => {
    const nodes = asArray<GraphNode>(deps.dataset.get());
    const hoverId = getHoverId();
    const selectedIds = getSelectionIds();
    const primarySelected = selectedIds.values().next().value as string | undefined;
    const relationFocus = hoverId || primarySelected || '';
    const related = getRelatedNodes(relationFocus);
    const hasHover = Boolean(hoverId);
    const hasSelection = selectedIds.size > 0;

    deps.container.dataset.hasHover = hasHover ? 'true' : 'false';
    deps.container.dataset.hasSelection = hasSelection ? 'true' : 'false';
    deps.container.setAttribute('data-has-hover', deps.container.dataset.hasHover);
    deps.container.setAttribute('data-has-selection', deps.container.dataset.hasSelection);
    deps.nodesRoot.innerHTML = '';
    deps.edgesRoot.innerHTML = '';
    deps.edgesRoot.setAttribute('aria-hidden', 'true');

    const sortedNodes = [...nodes].sort((a, b) => String(a.label ?? a.id).localeCompare(String(b.label ?? b.id)));
    for (let i = 0; i < sortedNodes.length; i += 1) {
      const nodeData = sortedNodes[i];
      const nodeId = toNodeId(nodeData.id);
      if (!nodeId) continue;
      const state = computeState(nodeId, hoverId, selectedIds, related);
      const node = document.createElement('div');
      node.className = 'd4-node';
      node.dataset.id = nodeId;
      node.dataset.state = state;
      node.style.left = `${Number(nodeData.x ?? 0)}px`;
      node.style.top = `${Number(nodeData.y ?? 0)}px`;
      node.style.cssText += nodeColorVars(Number(nodeData.group ?? 0));
      node.tabIndex = i === 0 ? 0 : -1;
      node.setAttribute('aria-label', `${nodeData.label ?? nodeId}, ${nodeData.type ?? 'Node'}, score ${Number(nodeData.score ?? 0)}`);
      node.textContent = String(nodeData.label ?? nodeId);
      deps.nodesRoot.appendChild(node);
    }

    const edges = asArray<GraphEdge>(deps.edgesDataset?.get());
    const nodeById = new Map<string, GraphNode>(nodes.map((n) => [toNodeId(n.id), n]));
    for (const edge of edges) {
      const [fromId, toId] = getEdgeEndpoints(edge);
      const sourceNode = nodeById.get(fromId);
      const targetNode = nodeById.get(toId);
      if (!sourceNode || !targetNode) continue;
      const line = document.createElementNS(SVG_NS, 'line');
      line.classList.add('d4-edge');
      line.setAttribute('x1', String(Number(sourceNode.x ?? 0)));
      line.setAttribute('y1', String(Number(sourceNode.y ?? 0)));
      line.setAttribute('x2', String(Number(targetNode.x ?? 0)));
      line.setAttribute('y2', String(Number(targetNode.y ?? 0)));
      line.style.setProperty('--node-color', `var(--wcc-c${Math.abs(Number(sourceNode.group ?? 0)) % 12})`);
      line.style.setProperty('--node-color-muted', COLOR_MUTED_BY_INDEX[Math.abs(Number(sourceNode.group ?? 0)) % 12]);
      const isRelated = relationFocus ? (fromId === relationFocus || toId === relationFocus) : true;
      line.dataset.related = isRelated ? 'true' : 'false';
      line.setAttribute('data-related', line.dataset.related);
      if (fromId && selectedIds.has(fromId)) line.dataset.emphasis = 'selected';
      else if (fromId && hoverId && fromId === hoverId) line.dataset.emphasis = 'hover';
      deps.edgesRoot.appendChild(line);
    }
  };

  const onKeyboard = (event: KeyboardEvent): void => {
    if (!ARROW_KEYS.includes(event.key)) return;
    const nodes = Array.from(deps.nodesRoot.querySelectorAll<HTMLElement>('.d4-node'));
    if (!nodes.length) return;
    const activeIndex = nodes.findIndex((node) => node.tabIndex === 0);
    const currentIndex = activeIndex >= 0 ? activeIndex : 0;
    const step = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1;
    const nextIndex = (currentIndex + step + nodes.length) % nodes.length;
    nodes.forEach((node, idx) => {
      node.tabIndex = idx === nextIndex ? 0 : -1;
    });
    nodes[nextIndex].focus();
    event.preventDefault();
  };

  const onDatasetUpdate = (): void => renderAll();
  deps.nodesRoot.addEventListener('keydown', onKeyboard);
  const unsubscribe = deps.dataset._subscribe ? deps.dataset._subscribe(onDatasetUpdate) : undefined;
  const unsubscribeEdges = deps.edgesDataset?._subscribe ? deps.edgesDataset._subscribe(onDatasetUpdate) : undefined;
  renderAll();

  return {
    unmount(): void {
      if (typeof unsubscribe === 'function') unsubscribe();
      if (typeof unsubscribeEdges === 'function') unsubscribeEdges();
      deps.nodesRoot.removeEventListener('keydown', onKeyboard);
      deps.nodesRoot.innerHTML = '';
      deps.edgesRoot.innerHTML = '';
    },
  };
}
