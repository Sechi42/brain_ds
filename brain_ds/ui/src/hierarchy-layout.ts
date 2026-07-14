export interface HierarchyNode { id: string; parent_id?: string | null; [key: string]: unknown }
export interface HierarchyForest { nodes: Map<string, HierarchyNode>; children: Map<string, string[]>; parent: Map<string, string>; roots: string[] }
export interface HierarchyBranch { nodes: HierarchyNode[]; edges: [string, string][]; rootId: string | null }

export function buildForest(input: HierarchyNode[], edges: Array<{ from?: string; to?: string }> = []): HierarchyForest {
  const nodes = new Map(input.filter((node) => node?.id != null).map((node) => [String(node.id), node]));
  const parent = new Map<string, string>();
  const children = new Map<string, string[]>();
  const links = input.some((node) => node.parent_id != null)
    ? input.map((node) => [node.parent_id, node.id])
    : edges.map((edge) => [edge.from, edge.to]);
  const createsCycle = (child: string, candidate: string) => {
    for (let current: string | undefined = candidate; current; current = parent.get(current)) if (current === child) return true;
    return false;
  };
  for (const [rawParent, rawChild] of links) {
    const parentId = String(rawParent ?? ""), childId = String(rawChild ?? "");
    if (!parentId || parentId === childId || !nodes.has(parentId) || !nodes.has(childId) || parent.has(childId) || createsCycle(childId, parentId)) continue;
    parent.set(childId, parentId);
    children.set(parentId, [...(children.get(parentId) ?? []), childId].sort());
  }
  return { nodes, children, parent, roots: [...nodes.keys()].filter((id) => !parent.has(id)).sort() };
}

export function branchFor(forest: HierarchyForest, selectedId: string | null): HierarchyBranch {
  if (!selectedId || !forest.nodes.has(selectedId)) return { nodes: [], edges: [], rootId: null };
  const included = new Set<string>();
  const ancestors: string[] = [];
  for (let current: string | undefined = selectedId; current; current = forest.parent.get(current)) { included.add(current); ancestors.unshift(current); }
  const queue = [selectedId];
  const descendants: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    if (id !== selectedId) descendants.push(id);
    for (const child of forest.children.get(id) ?? []) if (!included.has(child)) { included.add(child); queue.push(child); }
  }
  const ids = [...ancestors, ...descendants];
  const nodes = ids.map((id) => forest.nodes.get(id)!);
  const edges: [string, string][] = [];
  for (const id of ids) for (const child of forest.children.get(id) ?? []) if (included.has(child)) edges.push([id, child]);
  let rootId = selectedId;
  while (forest.parent.has(rootId)) rootId = forest.parent.get(rootId)!;
  return { nodes, edges, rootId };
}

export function layout(branch: HierarchyBranch) {
  const depth = new Map<string, number>();
  const byParent = new Map(branch.edges.map(([parent, child]) => [child, parent]));
  let maxDepth = 0;
  for (const node of branch.nodes) {
    let value = 0;
    for (let current = node.id; byParent.has(current); current = byParent.get(current)!) value += 1;
    depth.set(node.id, value); maxDepth = Math.max(maxDepth, value);
  }
  const positions = branch.nodes.map((node, index) => ({ id: node.id, depth: depth.get(node.id) ?? 0, row: index }));
  return { positions, width: 280 + maxDepth * 250, height: Math.max(152, 96 + positions.length * 56) };
}
