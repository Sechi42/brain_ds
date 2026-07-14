import { applyTypeColor, type TypeColor } from "../type-color";

type TreeNode = {
  id: string;
  label?: string;
  type?: string;
  supertype?: string;
  parent_id?: string | null;
  depth?: number;
  color?: TypeColor;
};

type MountDeps = {
  nodes: TreeNode[];
  typeGroups?: Array<{ supertype: string; types: Array<{ type: string; count?: number; color?: TypeColor }> }>;
  onFilter: (nodeId: string | null) => void;
  onActiveLabel?: (label: string) => void;
  onNodeFocus?: (nodeId: string) => void;
};

const CHEVRON_SVG = '<svg aria-hidden="true" width="14" height="14"><use href="#icon-chevron-right"/></svg>';

function makeChip(color: TypeColor): HTMLSpanElement {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.setAttribute("aria-hidden", "true");
  applyTypeColor(chip, color);
  return chip;
}

const listeners: Array<() => void> = [];
const expandedGroups = new Set<string>();

function isInternalNode(node: TreeNode): boolean {
  return node.supertype === "data-internal" || node.type === "DataContainer" || node.type === "DataField";
}

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
  const groupedTypes = Array.isArray(deps.typeGroups) ? deps.typeGroups : [];
  const hasTypeGroups = groupedTypes.length > 0;
  if (hasTypeGroups) {
    const byType = new Map<string, TreeNode[]>();
    nodes.forEach((node) => {
      const typeName = String(node.type || "Unknown");
      if (!byType.has(typeName)) byType.set(typeName, []);
      byType.get(typeName)!.push(node);
    });

    groupedTypes.forEach((group) => {
      const section = document.createElement("section");
      section.className = "tree-group";
      section.setAttribute("data-hierarchy-group", group.supertype);

      const heading = document.createElement("h4");
      heading.className = "tree-group-heading";
      heading.textContent = String(group.supertype || "Grupo").toUpperCase();
      section.appendChild(heading);

      group.types.forEach((typeEntry) => {
        const typeName = String(typeEntry.type || "Unknown");
        const typeNodes = byType.get(typeName) || [];
        const typeKey = `${group.supertype}:${typeName}`;
        const isExpanded = expandedGroups.has(typeKey);

        const row = document.createElement("div");
        row.className = "tree-item";
        row.setAttribute("data-hierarchy-type", typeName);

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "tree-toggle";
        toggle.innerHTML = CHEVRON_SVG;
        toggle.setAttribute("aria-expanded", isExpanded ? "true" : "false");
        toggle.setAttribute("aria-label", `${isExpanded ? "Contraer" : "Expandir"} ${typeName}`);
        const onToggle = () => {
          if (expandedGroups.has(typeKey)) expandedGroups.delete(typeKey);
          else expandedGroups.add(typeKey);
          mount(root, deps);
        };
        toggle.addEventListener("click", onToggle);
        listeners.push(() => toggle.removeEventListener("click", onToggle));
        row.appendChild(toggle);

        const typeBtn = document.createElement("button");
        typeBtn.type = "button";
        typeBtn.className = "tree-node";
        typeBtn.appendChild(makeChip(typeEntry.color || (typeNodes[0] && typeNodes[0].color)));
        const typeLabel = document.createElement("span");
        typeLabel.className = "tree-node-label";
        typeLabel.textContent = typeName;
        typeBtn.appendChild(typeLabel);
        const countPill = document.createElement("span");
        countPill.className = "tree-node-count";
        countPill.textContent = String(typeNodes.length || Number(typeEntry.count || 0));
        typeBtn.appendChild(countPill);
        row.appendChild(typeBtn);
        section.appendChild(row);

        if (isExpanded && typeNodes.length) {
          const nodeList = document.createElement("div");
          nodeList.className = "tree-group-list";
          typeNodes.forEach((node) => {
            const nodeBtn = document.createElement("button");
            nodeBtn.type = "button";
            nodeBtn.className = "tree-node";
            nodeBtn.style.marginLeft = "28px";
            nodeBtn.textContent = String(node.label || node.id);
            nodeBtn.prepend(makeChip(node.color));
            const onClick = () => {
              if (typeof deps.onNodeFocus === "function") deps.onNodeFocus(String(node.id));
              if (deps.onActiveLabel) deps.onActiveLabel(String(node.label || node.id));
            };
            nodeBtn.addEventListener("click", onClick);
            listeners.push(() => nodeBtn.removeEventListener("click", onClick));
            nodeList.appendChild(nodeBtn);
          });
          section.appendChild(nodeList);
        }
      });

      root.appendChild(section);
    });
    return;
  }

  const byParent = new Map<string | null, TreeNode[]>();
  nodes.forEach((node) => {
    const pid = isInternalNode(node) && node.parent_id != null ? String(node.parent_id) : null;
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
        toggle.innerHTML = CHEVRON_SVG;
        toggle.setAttribute("aria-expanded", expanded.has(id) ? "true" : "false");
        toggle.setAttribute("aria-label", `${expanded.has(id) ? "Contraer" : "Expandir"} ${String(node.label || node.id)}`);
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
      action.prepend(makeChip(node.color));
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
