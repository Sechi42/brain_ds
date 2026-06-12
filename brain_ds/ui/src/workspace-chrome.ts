// @ts-nocheck
// workspace-chrome.ts — Stateful rail panel routing for the workspace shell chrome.
// Slice 1 (P0): rail panel routing + mount/unmount lifecycle + keyboard nav.
// Slice 2 (P1): overflow menu (to be added in follow-up PR).
//
// Follows the module-level-state + _listeners[] teardown pattern
// established by detail-panel.ts and context-menu.ts.

export interface WorkspaceChromeDeps {
  railRoot: HTMLElement;   // <nav role="tablist"> containing [data-rail-icon] buttons
  panelRoot: HTMLElement;  // <aside> containing [data-accordion-section] sections
  overflowButton?: HTMLElement | null;
  resetFilters?: () => void;
  exportJson?: () => void;
  toggleTheme?: () => void;
}

// Rail icon names — defines the ordered tablist.
// "navigator" removed (duplicates file-tree/projects functionality).
const RAIL_NAMES = ["file-tree", "search", "filters", "hierarchy", "layout"] as const;
type RailName = (typeof RAIL_NAMES)[number];

// Module-level state — single instance per page.
let _deps: WorkspaceChromeDeps | null = null;
let _activePanel: string = "file-tree";
let _listeners: Array<{
  target: EventTarget;
  type: string;
  handler: EventListenerOrEventListenerObject;
  options?: boolean | AddEventListenerOptions;
}> = [];
let _overflowMenuEl: HTMLElement | null = null;
let _lastOverflowTrigger: HTMLElement | null = null;

function _setOverflowExpanded(expanded: boolean): void {
  const trigger = _deps?.overflowButton || null;
  if (!trigger) return;
  trigger.setAttribute("aria-expanded", expanded ? "true" : "false");
}

function _closeOverflowMenu(restoreFocus: boolean): void {
  if (_overflowMenuEl && _overflowMenuEl.parentNode) {
    _overflowMenuEl.parentNode.removeChild(_overflowMenuEl);
  }
  _overflowMenuEl = null;
  _setOverflowExpanded(false);
  if (restoreFocus && _lastOverflowTrigger && typeof _lastOverflowTrigger.focus === "function") {
    _lastOverflowTrigger.focus();
  }
}

function _moveMenuFocus(delta: number): void {
  if (!_overflowMenuEl) return;
  const menuItems = Array.from(_overflowMenuEl.querySelectorAll('[role="menuitem"]')) as HTMLElement[];
  if (!menuItems.length) return;
  const active = (typeof document !== "undefined" ? document.activeElement : null) as HTMLElement | null;
  const current = Math.max(0, menuItems.indexOf(active as HTMLElement));
  const next = (current + delta + menuItems.length) % menuItems.length;
  menuItems[next].focus();
}

function _openOverflowMenu(trigger: HTMLElement): void {
  _closeOverflowMenu(false);
  _lastOverflowTrigger = trigger;

  const menu = document.createElement("div");
  menu.setAttribute("role", "menu");
  menu.className = "workspace-overflow-menu";
  menu.style.position = "fixed";
  menu.style.zIndex = "2000";

  const rect = trigger.getBoundingClientRect();
  const minWidth = 180;
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1280;
  const viewportHeight = typeof window !== "undefined" ? window.innerHeight : 800;
  const workspaceRect = (typeof document !== "undefined"
    ? document.querySelector(".center-column")?.getBoundingClientRect()
    : null) || { left: 8, top: 8, right: viewportWidth - 8, bottom: viewportHeight - 8 };
  const leftMin = Math.max(8, Math.round(workspaceRect.left) + 8);
  const leftMax = Math.max(leftMin, Math.round(workspaceRect.right) - minWidth - 8);
  const rawLeft = Math.round(rect.right - minWidth);
  const rawTop = Math.round(rect.bottom + 8);
  const clampedLeft = Math.min(leftMax, Math.max(leftMin, rawLeft));
  const maxTop = Math.max(8, Math.round(workspaceRect.bottom) - 140);
  const clampedTop = Math.min(maxTop, Math.max(Math.round(workspaceRect.top) + 8, rawTop));
  menu.style.top = `${clampedTop}px`;
  menu.style.left = `${clampedLeft}px`;
  menu.style.minWidth = `${minWidth}px`;

  const actions: Array<{ label: string; onClick: () => void }> = [
    { label: "Reset filters", onClick: () => _deps?.resetFilters?.() },
    { label: "Export JSON", onClick: () => _deps?.exportJson?.() },
    { label: "Toggle theme", onClick: () => _deps?.toggleTheme?.() },
  ];

  for (const action of actions) {
    const item = document.createElement("button");
    item.type = "button";
    item.setAttribute("role", "menuitem");
    item.textContent = action.label;
    item.addEventListener("click", () => {
      action.onClick();
      _closeOverflowMenu(true);
    });
    menu.appendChild(item);
  }

  menu.addEventListener("keydown", (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      _closeOverflowMenu(true);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      _moveMenuFocus(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      _moveMenuFocus(-1);
    }
  });

  document.body.appendChild(menu);
  _overflowMenuEl = menu;
  _setOverflowExpanded(true);

  const menuItems = Array.from(menu.querySelectorAll('[role="menuitem"]')) as HTMLElement[];
  if (menuItems.length) menuItems[0].focus();
}

/**
 * Return all rail icon buttons in tablist order.
 */
function _getRailButtons(): HTMLElement[] {
  if (!_deps) return [];
  return RAIL_NAMES.map((name) => {
    const btn = _deps!.railRoot.querySelector(`[data-rail-icon="${name}"]`) as HTMLElement | null;
    return btn;
  }).filter(Boolean) as HTMLElement[];
}

/**
 * Return all accordion section elements.
 */
function _getSections(): HTMLElement[] {
  if (!_deps) return [];
  const all = _deps!.panelRoot.querySelectorAll("[data-accordion-section]");
  return Array.from(all) as HTMLElement[];
}

/**
 * setActivePanel — set the active panel by name.
 *
 * Side effects (in order per design ADR):
 *   (a) aria-selected: true on active, false on others
 *   (b) roving tabindex: 0 on active, -1 on others
 *   (c) section visibility groups:
 *       - "file-tree" / "search" → search (+ score helper)
 *       - "filters" → filters + legend
 *       - "hierarchy" → hierarchy
 *       - "layout" → layout
 *
 * Idempotent: re-applying the active panel is a no-op.
 */
export function setActivePanel(name: string): void {
  if (!_deps) return;

  _activePanel = name;

  const buttons = _getRailButtons();
  const sections = _getSections();

  // (a) + (b): aria-selected + roving tabindex
  for (const btn of buttons) {
    const isActive = btn.getAttribute("data-rail-icon") === name;
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    btn.setAttribute("tabindex", isActive ? "0" : "-1");
  }

  // (c): section visibility
  const sectionGroups: Record<string, Set<string>> = {
    "file-tree": new Set(["projects"]),
    "search": new Set(["search", "score"]),
    "filters": new Set(["filters", "legend"]),
    "hierarchy": new Set(["hierarchy"]),
    "layout": new Set(["layout"]),
  };
  const visible = sectionGroups[name] || sectionGroups["file-tree"];
  for (const sec of sections) {
    const sectionName = String(sec.getAttribute("data-accordion-section") || "");
    const show = visible.has(sectionName);
    sec.hidden = !show;
    sec.setAttribute("aria-hidden", show ? "false" : "true");
  }
}

/**
 * mount — initialize workspace-chrome with DOM references.
 * Wires click and keyboard (ArrowDown/Up/Home/End) handlers on the rail.
 */
export function mount(deps: WorkspaceChromeDeps): void {
  _deps = deps;
  _activePanel = "file-tree";

  // Apply initial state (file-tree active by default)
  setActivePanel("file-tree");

  // Click handler on railRoot (event delegation)
  const clickHandler = (event: MouseEvent) => {
    const target = event.target as HTMLElement;
    const btn = target.closest("[data-rail-icon]") as HTMLElement | null;
    if (!btn) return;
    const name = btn.getAttribute("data-rail-icon");
    if (!name) return;
    setActivePanel(name);
  };
  _deps.railRoot.addEventListener("click", clickHandler);
  _listeners.push({ target: _deps.railRoot, type: "click", handler: clickHandler });

  // Keyboard handler — WAI-ARIA APG vertical tablist with automatic activation
  const keydownHandler = (event: KeyboardEvent) => {
    const buttons = _getRailButtons();
    const currentIndex = buttons.findIndex(
      (btn) => btn.getAttribute("data-rail-icon") === _activePanel
    );
    let nextIndex = -1;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      nextIndex = (currentIndex + 1) % buttons.length;
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
    } else if (event.key === "Home") {
      event.preventDefault();
      nextIndex = 0;
    } else if (event.key === "End") {
      event.preventDefault();
      nextIndex = buttons.length - 1;
    }

    if (nextIndex >= 0) {
      const name = buttons[nextIndex].getAttribute("data-rail-icon");
      if (name) {
        setActivePanel(name);
        buttons[nextIndex].focus();
      }
    }
  };
  _deps.railRoot.addEventListener("keydown", keydownHandler);
  _listeners.push({ target: _deps.railRoot, type: "keydown", handler: keydownHandler });

  const overflowTrigger = _deps.overflowButton || null;
  if (overflowTrigger) {
    (window as any).__brainDsOverflowManaged = true;
    const overflowClickHandler = (event: MouseEvent) => {
      event.preventDefault();
      const expanded = overflowTrigger.getAttribute("aria-expanded") === "true";
      if (expanded) {
        _closeOverflowMenu(false);
      } else {
        _openOverflowMenu(overflowTrigger);
      }
    };
    overflowTrigger.addEventListener("click", overflowClickHandler);
    _listeners.push({ target: overflowTrigger, type: "click", handler: overflowClickHandler });

    const dismissOnOutside = (event: Event) => {
      if (!_overflowMenuEl) return;
      const target = event.target as Node | null;
      if (!target) return;
      if (_overflowMenuEl.contains(target)) return;
      if (overflowTrigger.contains(target)) return;
      _closeOverflowMenu(false);
    };
    document.addEventListener("pointerdown", dismissOnOutside, true);
    _listeners.push({ target: document, type: "pointerdown", handler: dismissOnOutside, options: true });
  }
}

/**
 * unmount — remove all event listeners and reset module state.
 */
export function unmount(): void {
  _closeOverflowMenu(false);
  if (typeof window !== "undefined") {
    (window as any).__brainDsOverflowManaged = false;
  }
  _listeners.forEach(({ target, type, handler, options }) => {
    if (target && typeof (target as any).removeEventListener === "function") {
      (target as any).removeEventListener(type, handler, options);
    }
  });
  _listeners = [];
  _deps = null;
  _activePanel = "file-tree";
  _lastOverflowTrigger = null;
}
