// @ts-nocheck
/**
 * panels/filter-panel.ts
 *
 * Type-filter checkboxes + legend DOM construction.
 * Design binding: §1.2 — mount(root, deps) / unmount() shape.
 * No React, no lifecycle library — vanilla TS function with teardown.
 *
 * PR 5: extraction from graph_viewer.html inline script.
 * Ports verbatim: typeGroups.forEach loop (filter items + legend items),
 *   toggleType helper, show-all / hide-all button wiring.
 *
 * Deps shape (passed from template via mount()):
 *   typeGroups: TypeGroup[]          — from RENDER_CONTEXT.type_groups
 *   filtersRoot: HTMLElement         — #type-filters div
 *   legendRoot: HTMLElement          — #legend div
 *   showAllBtn: HTMLElement          — #show-all button
 *   hideAllBtn: HTMLElement          — #hide-all button
 *   onToggle: (typeName: string, enabled: boolean) => void
 *                                    — called when a type is toggled
 *   onShowAll: () => void            — called when show-all clicked
 *   onHideAll: () => void            — called when hide-all clicked
 */

// ── Types ──────────────────────────────────────────────────────────────────

export interface TypeEntry {
  type: string;
  color: string;
  count: number;
}

export interface TypeGroup {
  supertype: string;
  types: TypeEntry[];
}

export interface FilterPanelDeps {
  typeGroups: TypeGroup[];
  filtersRoot: HTMLElement;
  legendRoot: HTMLElement;
  showAllBtn: HTMLElement | null;
  hideAllBtn: HTMLElement | null;
  onToggle: (typeName: string, enabled: boolean) => void;
  onShowAll: () => void;
  onHideAll: () => void;
}

// ── Module state ────────────────────────────────────────────────────────────

let _deps: FilterPanelDeps | null = null;
let _typeCheckboxes: Map<string, HTMLInputElement> = new Map();
let _listeners: Array<{ el: EventTarget; type: string; fn: EventListener }> = [];

// ── Helpers ─────────────────────────────────────────────────────────────────

function _addListener(el: EventTarget, type: string, fn: EventListener): void {
  el.addEventListener(type, fn);
  _listeners.push({ el, type, fn });
}

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * mount — initialize the filter panel.
 *
 * Builds all filter checkboxes and legend items from typeGroups.
 * Wires show-all / hide-all buttons.
 * Sets up change listeners on checkboxes.
 */
export function mount(deps: FilterPanelDeps): void {
  _deps = deps;
  _typeCheckboxes = new Map();
  _listeners = [];

  const { typeGroups, filtersRoot, legendRoot, showAllBtn, hideAllBtn, onToggle, onShowAll, onHideAll } = deps;

  // ── Build type filter checkboxes + legend items ───────────────────────────
  typeGroups.forEach((group) => {
    const h = document.createElement("h3");
    h.textContent = group.supertype;
    filtersRoot.appendChild(h);

    group.types.forEach((t) => {
      // Filter item: checkbox + color chip + label with count
      const label = document.createElement("label");
      label.className = "filter-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = true;
      _addListener(cb, "change", () => {
        onToggle(t.type, cb.checked);
      });
      _typeCheckboxes.set(t.type, cb);

      const chip = document.createElement("span");
      chip.className = "chip";
      chip.style.background = t.color;

      label.appendChild(cb);
      label.appendChild(chip);
      label.appendChild(document.createTextNode(`${t.type} (${t.count})`));
      filtersRoot.appendChild(label);

      // Legend item: button with chip + type name
      const legendItem = document.createElement("div");
      legendItem.className = "legend-item";
      const legendBtn = document.createElement("button");
      legendBtn.type = "button";
      legendBtn.innerHTML = `<span class='chip' style='background:${t.color}'></span> ${t.type}`;
      _addListener(legendBtn, "click", () => {
        // Toggle: if type is currently hidden, show it; if shown, hide it.
        // The onToggle callback handles the hiddenTypes Set.
        const currentCb = _typeCheckboxes.get(t.type);
        const isCurrentlyHidden = currentCb ? !currentCb.checked : false;
        onToggle(t.type, isCurrentlyHidden);
        if (currentCb) currentCb.checked = isCurrentlyHidden;
      });
      legendItem.appendChild(legendBtn);
      legendRoot.appendChild(legendItem);
    });
  });

  // ── Show-all / Hide-all button wiring ─────────────────────────────────────
  if (showAllBtn) {
    _addListener(showAllBtn, "click", () => {
      _typeCheckboxes.forEach((cb) => { cb.checked = true; });
      onShowAll();
    });
  }

  if (hideAllBtn) {
    _addListener(hideAllBtn, "click", () => {
      _typeCheckboxes.forEach((cb, typeName) => {
        cb.checked = false;
        onToggle(typeName, false);
      });
      onHideAll();
    });
  }
}

/**
 * getTypeCheckboxes — returns the checkbox Map for external callers
 * (e.g., resetFilters in template that needs to set all checkboxes checked).
 */
export function getTypeCheckboxes(): Map<string, HTMLInputElement> {
  return _typeCheckboxes;
}

/**
 * setAllChecked — set all checkboxes to checked or unchecked.
 * Used by show-all / reset-filters sequences.
 */
export function setAllChecked(checked: boolean): void {
  _typeCheckboxes.forEach((cb) => { cb.checked = checked; });
}

/**
 * unmount — remove all event listeners and clear module state.
 */
export function unmount(): void {
  _listeners.forEach(({ el, type, fn }) => el.removeEventListener(type, fn));
  _listeners = [];
  _deps = null;
  _typeCheckboxes = new Map();
}
