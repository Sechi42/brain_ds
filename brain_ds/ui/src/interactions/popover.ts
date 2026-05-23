// @ts-nocheck
// Hover popover content factory for the graph viewer.
// PR 6 extraction: moves popover content construction from renderer.ts default builder
// to this module via the setPopoverContentFactory API (renderer.ts Slice 4 hook).
// The renderer's DOM structure (_popoverEl, show/hide/position logic) stays in renderer.ts.
// This module provides a content factory that produces equivalent HTML to the default.

export interface PopoverNode {
  id: any;
  label?: string;
  type?: string;
  group?: string;
  score?: number | null;
  source?: string;
}

export interface PopoverDeps {
  network: any;
  RENDER_CONTEXT: any;
}

// Module-level state.
let _deps: PopoverDeps | null = null;
let _listeners: Array<{ target: EventTarget; type: string; handler: EventListenerOrEventListenerObject }> = [];

export function mount(deps: PopoverDeps): void {
  _deps = deps;
  if (deps.network) {
    deps.network.hoverDelayMs = 150;
  }

  // Register the content factory with the renderer.
  if (typeof deps.network.setPopoverContentFactory === "function") {
    deps.network.setPopoverContentFactory(createContentFactory(deps));
  }
}

export function unmount(): void {
  _listeners.forEach(({ target, type, handler }) => {
    if (target && typeof (target as any).removeEventListener === "function") {
      (target as any).removeEventListener(type, handler);
    }
  });
  _listeners = [];
  _deps = null;
}

// Content factory — returns a function that accepts nodeId and returns an HTMLElement.
// Produces equivalent content to the renderer.ts default builder:
//   <strong class="vis-popover-name">{label}</strong>
//   <span class="vis-popover-type">{type}</span>
//   <span class="vis-popover-score">Score: {score.toFixed(2)}</span>
//   <span class="vis-popover-source">Source: {source}</span>
// Each field is conditional: only rendered when the node has that property.
export function createContentFactory(deps: PopoverDeps): (nodeId: any) => HTMLElement | null {
  return function (nodeId: any): HTMLElement | null {
    const nodes = (deps.RENDER_CONTEXT && deps.RENDER_CONTEXT.nodes) || [];
    const node: PopoverNode | undefined = nodes.find(
      (n: PopoverNode) => String(n.id) === String(nodeId)
    );
    if (!node) return null;

    const adjacency = (deps.RENDER_CONTEXT && deps.RENDER_CONTEXT.adjacency) || {};
    const neighbors = Array.isArray(adjacency[String(node.id)]) ? adjacency[String(node.id)].length : 0;
    const cluster = node.group !== undefined && node.group !== null ? String(node.group) : "N/A";
    const scoreValue = node.score !== undefined && node.score !== null ? Number(node.score).toFixed(2) : "N/A";

    const container = document.createElement("div");
    container.className = "vis-popover-content";

    const title = document.createElement("div");
    title.className = "hover-popover-title";

    const dot = document.createElement("span");
    dot.className = "hover-popover-dot";
    dot.setAttribute("aria-hidden", "true");
    title.appendChild(dot);

    const nameEl = document.createElement("strong");
    nameEl.className = "vis-popover-name";
    nameEl.textContent = String(node.label || node.id);
    title.appendChild(nameEl);
    container.appendChild(title);

    const grid = document.createElement("dl");
    grid.className = "hover-popover-grid";

    const appendMetric = (label: string, value: string): void => {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value;
      grid.appendChild(term);
      grid.appendChild(detail);
    };

    appendMetric("Score", scoreValue);
    appendMetric("Neighbors", String(neighbors));
    appendMetric("Cluster", cluster);
    appendMetric("Type", String(node.type || "Node"));
    container.appendChild(grid);

    const hint = document.createElement("span");
    hint.className = "hover-popover-hint";
    hint.textContent = "Enter to select";
    container.appendChild(hint);

    if (node.type || node.group) {
      const typeEl = document.createElement("span");
      typeEl.className = "vis-popover-type";
      typeEl.textContent = String(node.type || node.group);
      container.appendChild(typeEl);
    }

    if (node.score !== undefined && node.score !== null) {
      const scoreEl = document.createElement("span");
      scoreEl.className = "vis-popover-score";
      scoreEl.textContent = "Score: " + scoreValue;
      container.appendChild(scoreEl);
    }

    if (node.source) {
      const sourceEl = document.createElement("span");
      sourceEl.className = "vis-popover-source";
      sourceEl.textContent = "Source: " + String(node.source);
      container.appendChild(sourceEl);
    }

    return container;
  };
}
