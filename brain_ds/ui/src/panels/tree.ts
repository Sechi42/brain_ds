type TreeNode = {
  id: string;
  label?: string;
  parent_id?: string | null;
  depth?: number;
};

type MountDeps = {
  nodes: TreeNode[];
  onFilter: (nodeId: string | null) => void;
  onActiveLabel?: (label: string) => void;
};

const listeners: Array<() => void> = [];

export function unmount(): void {
  while (listeners.length) {
    const dispose = listeners.pop();
    if (dispose) dispose();
  }
}

export function mount(root: HTMLElement | null, deps: MountDeps): void {
  if (!root || !deps) return;
  unmount();
  root.innerHTML = "";

  const nodes = Array.isArray(deps.nodes) ? deps.nodes : [];
  const byParent = new Map<string | null, TreeNode[]>();
  nodes.forEach((node) => {
    const pid = node.parent_id == null ? null : String(node.parent_id);
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid)!.push(node);
  });

  const expanded = new Set<string>();
  const roots = byParent.get(null) || [];
  roots.forEach((n) => expanded.add(String(n.id)));

  const renderBranch = (parentId: string | null, host: HTMLElement): void => {
    const branch = byParent.get(parentId) || [];
    branch.forEach((node) => {
      const id = String(node.id);
      const children = byParent.get(id) || [];
      const row = document.createElement("div");
      row.className = "tree-item";
      row.style.marginLeft = `${Math.max(0, Number(node.depth || 0)) * 12}px`;

      if (children.length > 0) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "tree-toggle";
        toggle.textContent = expanded.has(id) ? "▾" : "▸";
        toggle.setAttribute("aria-expanded", expanded.has(id) ? "true" : "false");
        const onToggle = () => {
          if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
          mount(root, deps);
        };
        toggle.addEventListener("click", onToggle);
        listeners.push(() => toggle.removeEventListener("click", onToggle));
        row.appendChild(toggle);
      }

      const action = document.createElement("button");
      action.type = "button";
      action.className = "tree-node";
      action.textContent = String(node.label || node.id);
      const onClick = () => {
        deps.onFilter(node.parent_id == null ? null : id);
        if (deps.onActiveLabel) deps.onActiveLabel(String(node.label || node.id));
      };
      action.addEventListener("click", onClick);
      listeners.push(() => action.removeEventListener("click", onClick));
      row.appendChild(action);

      host.appendChild(row);
      if (children.length > 0 && expanded.has(id)) {
        renderBranch(id, host);
      }
    });
  };

  renderBranch(null, root);
}
