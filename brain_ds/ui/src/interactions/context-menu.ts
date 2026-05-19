// @ts-nocheck
// Context menu DOM construction + keyboard navigation for the graph viewer.
// PR 6 extraction: moves context-menu code from template inline script to this module.
// The renderer's 'context-menu' event is emitted by renderer.ts (_onContextMenu) and
// subscribed via network.on('context-menu', ...) in the template mount call.

export interface ContextMenuDeps {
  network: any;
  RENDER_CONTEXT: any;
  adjacency: Record<string, string[]>;
  nodes: any;
  edges: any;
  focusNode: (nodeId: any) => void;
  resetFilters: () => void;
  toggleTheme: () => void;
}

// Module-level state — single instance per page.
let _deps: ContextMenuDeps | null = null;
let _ctxMenuEl: HTMLElement | null = null;
let _listeners: Array<{ target: EventTarget; type: string; handler: EventListenerOrEventListenerObject; options?: boolean | AddEventListenerOptions }> = [];
let _contextMenuState = { open: false, x: 0, y: 0, target: null as any };

export function mount(deps: ContextMenuDeps): void {
  _deps = deps;

  // Create the shared context-menu overlay element.
  _ctxMenuEl = document.createElement("div");
  _ctxMenuEl.id = "vis-context-menu";
  _ctxMenuEl.setAttribute("role", "menu");
  _ctxMenuEl.setAttribute("aria-label", "Context menu");
  _ctxMenuEl.className = "vis-context-menu";
  _ctxMenuEl.style.position = "fixed";
  _ctxMenuEl.style.zIndex = "2000";
  _ctxMenuEl.style.display = "none";
  _ctxMenuEl.style.outline = "none";
  document.body.appendChild(_ctxMenuEl);

  // Keyboard nav: ArrowDown, ArrowUp, Escape.
  const keydownHandler = (event: KeyboardEvent) => {
    const items = Array.from(_ctxMenuEl!.querySelectorAll("button:not([disabled])")) as HTMLElement[];
    const idx = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (idx < items.length - 1) items[idx + 1].focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (idx > 0) items[idx - 1].focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeContextMenu();
    }
  };
  _ctxMenuEl.addEventListener("keydown", keydownHandler);
  _listeners.push({ target: _ctxMenuEl, type: "keydown", handler: keydownHandler });

  // Click outside closes the menu (capture phase).
  const clickOutsideHandler = (event: MouseEvent) => {
    if (_ctxMenuEl && _ctxMenuEl.style.display !== "none" && !_ctxMenuEl.contains(event.target as Node)) {
      closeContextMenu();
    }
  };
  document.addEventListener("click", clickOutsideHandler, { capture: true });
  _listeners.push({ target: document, type: "click", handler: clickOutsideHandler, options: { capture: true } });

  // Subscribe to renderer's 'context-menu' event.
  const contextMenuHandler = ({ nodeId, screen }: { nodeId: any; screen: { x: number; y: number } }) => {
    if (nodeId !== null && nodeId !== undefined) {
      openNodeContextMenu(nodeId, screen.x, screen.y);
    } else {
      openCanvasContextMenu(screen.x, screen.y);
    }
  };
  deps.network.on("context-menu", contextMenuHandler);
  _listeners.push({ target: deps.network as any, type: "context-menu", handler: contextMenuHandler });
}

export function unmount(): void {
  _listeners.forEach(({ target, type, handler, options }) => {
    if (target && typeof (target as any).removeEventListener === "function") {
      (target as any).removeEventListener(type, handler, options);
    } else if (target && typeof (target as any).off === "function") {
      (target as any).off(type, handler);
    }
  });
  _listeners = [];
  if (_ctxMenuEl && _ctxMenuEl.parentNode) {
    _ctxMenuEl.parentNode.removeChild(_ctxMenuEl);
  }
  _ctxMenuEl = null;
  _deps = null;
  _contextMenuState = { open: false, x: 0, y: 0, target: null };
}

// Close context menu and restore focus to canvas.
function closeContextMenu(): void {
  if (!_ctxMenuEl || !_deps) return;
  _ctxMenuEl.style.display = "none";
  _contextMenuState.open = false;
  const triggerEl = _contextMenuState.target as HTMLElement | null;
  if (typeof _deps.network !== "undefined") {
    if (typeof _deps.network.closeContextMenu === "function") {
      _deps.network.closeContextMenu();
    }
    if (_contextMenuState.target && typeof (_contextMenuState.target as HTMLElement).focus === "function") {
      (_contextMenuState.target as HTMLElement).focus();
    } else if (_deps.network.canvas) {
      _deps.network.canvas.focus();
    }
  }
  _contextMenuState.target = null;
}

// Build a single menu item button element.
function makeMenuItem(label: string, icon: string, onClick: () => void, disabled = false, danger = false): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.setAttribute("role", "menuitem");
  const iconEl = document.createElement("span");
  iconEl.className = "vis-context-menu__icon";
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.innerHTML = `<svg aria-hidden="true"><use href="#icon-${icon}"/></svg>`;
  const textEl = document.createElement("span");
  textEl.className = "vis-context-menu__label";
  textEl.textContent = label;
  btn.appendChild(iconEl);
  btn.appendChild(textEl);
  btn.className = "vis-context-menu__item" + (disabled ? " vis-context-menu__item--disabled" : "") + (danger ? " menu-item--danger" : "");
  if (disabled) {
    btn.setAttribute("aria-disabled", "true");
    btn.disabled = true;
  }
  if (!disabled) {
    btn.addEventListener("click", () => {
      closeContextMenu();
      onClick();
    });
    btn.addEventListener("mouseenter", () => { btn.classList.add("vis-context-menu__item--hovered"); });
    btn.addEventListener("mouseleave", () => { btn.classList.remove("vis-context-menu__item--hovered"); });
  }
  return btn;
}

// Position the menu within viewport bounds (flip logic matching popover — REQ-6.4).
function positionMenu(clientX: number, clientY: number): void {
  if (!_ctxMenuEl) return;
  _contextMenuState.target = document.activeElement;
  _ctxMenuEl.style.left = "0px";
  _ctxMenuEl.style.top = "0px";
  _ctxMenuEl.style.display = "block";
  _contextMenuState.open = true;
  const w = _ctxMenuEl.offsetWidth || 210;
  const h = _ctxMenuEl.offsetHeight || 180;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = clientX;
  let top = clientY;
  if (left + w > vw) left = Math.max(0, clientX - w);
  if (top + h > vh) top = Math.max(0, clientY - h);
  _ctxMenuEl.style.left = left + "px";
  _ctxMenuEl.style.top = top + "px";
  // Move focus to first enabled item (REQ-6.8 / OBS-6.9).
  const first = _ctxMenuEl.querySelector("button:not([disabled])") as HTMLElement | null;
  if (first) first.focus();
}

// Build and show the NODE context menu.
function openNodeContextMenu(nodeId: any, clientX: number, clientY: number): void {
  if (!_ctxMenuEl || !_deps) return;
  _ctxMenuEl.innerHTML = "";
  const nodeData = (_deps.RENDER_CONTEXT.nodes || []).find(
    (n: any) => String(n.id) === String(nodeId)
  );

  // "Focus this node" — recenters viewport on node.
  _ctxMenuEl.appendChild(makeMenuItem("Focus this node", "target", () => {
    _deps!.focusNode(nodeId);
  }));

  // "Show only this node + neighbors" — ad-hoc 1-hop filter.
  _ctxMenuEl.appendChild(makeMenuItem("Show only this node + neighbors", "filter", () => {
    const neighbors = new Set(_deps!.adjacency[nodeId] || []);
    neighbors.add(String(nodeId));
    _deps!.nodes.update((_deps!.RENDER_CONTEXT.nodes || []).map((n: any) => ({
      id: n.id,
      hidden: !neighbors.has(String(n.id)),
    })));
    _deps!.edges.update((_deps!.RENDER_CONTEXT.edges || []).map((e: any, i: number) => ({
      id: i,
      hidden: !(neighbors.has(String(e.from)) && neighbors.has(String(e.to))),
    })));
  }));

  // "Copy entity JSON to clipboard".
  _ctxMenuEl.appendChild(makeMenuItem("Copy entity JSON to clipboard", "copy", () => {
    const payload = JSON.stringify(nodeData || { id: nodeId }, null, 2);
    navigator.clipboard.writeText(payload).then(() => {
      const liveRegion = document.querySelector("[aria-live='polite']");
      if (liveRegion) liveRegion.textContent = "Copied";
    });
  }));

  // "Open detail panel".
  _ctxMenuEl.appendChild(makeMenuItem("Open detail panel", "info", () => {
    _deps!.focusNode(nodeId);
  }));

  positionMenu(clientX, clientY);
}

// Build and show the CANVAS context menu.
function openCanvasContextMenu(clientX: number, clientY: number): void {
  if (!_ctxMenuEl || !_deps) return;
  _ctxMenuEl.innerHTML = "";

  // "Zoom to fit".
  _ctxMenuEl.appendChild(makeMenuItem("Zoom to fit", "search", () => {
    _deps!.network.fit({ animation: true });
  }));

  // "Reset filters".
  _ctxMenuEl.appendChild(makeMenuItem("Reset filters", "warning", () => {
    _deps!.resetFilters();
  }, false, true));

  const separator = document.createElement("hr");
  separator.className = "vis-context-menu__separator";
  _ctxMenuEl.appendChild(separator);

  // Layout section label.
  const layoutLabel = document.createElement("div");
  layoutLabel.className = "vis-context-menu__section-label";
  layoutLabel.textContent = "Switch layout";
  _ctxMenuEl.appendChild(layoutLabel);

  // "Force" layout (physics on).
  _ctxMenuEl.appendChild(makeMenuItem("  Force", "zap", () => {
    _deps!.network.setOptions({ layout: { hierarchical: { enabled: false } }, physics: { enabled: true } });
  }));

  // "Hierarchical" layout.
  _ctxMenuEl.appendChild(makeMenuItem("  Hierarchical", "layers", () => {
    _deps!.network.setOptions({ layout: { hierarchical: { enabled: true, direction: "UD" } }, physics: { enabled: false } });
  }));

  // "Grid (placeholder)" — always disabled (aria-disabled="true", REQ-6.9).
  const gridItem = makeMenuItem("  Grid (placeholder)", "grid", () => {}, true); // aria-disabled="true" set by makeMenuItem
  _ctxMenuEl.appendChild(gridItem);

  // "Toggle theme".
  _ctxMenuEl.appendChild(makeMenuItem("Toggle theme", "sun", () => {
    _deps!.toggleTheme();
  }));

  positionMenu(clientX, clientY);
}
