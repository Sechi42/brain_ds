// @ts-nocheck
import { applyTypeColor } from "../type-color";
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
  /** Ontology color — legacy string or the theme-aware payload from render_context. */
  color: string | { background?: string; dark?: string; light?: string };
  count: number;
}

export interface TypeGroup {
  supertype: string;
  types: TypeEntry[];
}

export interface SemanticClusterEntry {
  id: string;
  name: string;
  status?: string;
  lane_id?: string;
  member_node_ids?: string[];
}

export interface FilterPanelDeps {
  typeGroups: TypeGroup[];
  filtersRoot: HTMLElement;
  legendRoot: HTMLElement;
  showAllBtn?: HTMLElement | null;
  hideAllBtn?: HTMLElement | null;
  semanticClusters?: SemanticClusterEntry[];
  semanticClusterRoot?: HTMLElement | null;
  onToggle: (typeName: string, enabled: boolean) => void;
  onShowAll?: () => void;
  onHideAll?: () => void;
}

// ── Module state ────────────────────────────────────────────────────────────

let _deps: FilterPanelDeps | null = null;
let _typeCheckboxes: Map<string, HTMLInputElement> = new Map();
let _legendButtons: Map<string, HTMLButtonElement> = new Map();
let _listeners: Array<{ el: EventTarget; type: string; fn: EventListener }> = [];

// ── Helpers ─────────────────────────────────────────────────────────────────

function _addListener(el: EventTarget, type: string, fn: EventListener): void {
  el.addEventListener(type, fn);
  _listeners.push({ el, type, fn });
}

/**
 * Set the theme-aware type color pair as CSS custom properties.
 * render_context ships color as {background, dark, light}; assigning that
 * object to style.background silently failed and left swatches unpainted.
 * CSS resolves --type-color-dark / --type-color-light per [data-theme], so
 * theme switches recolor swatches without a re-render.
 */
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
  _legendButtons = new Map();
  _listeners = [];

  const { typeGroups, filtersRoot, legendRoot, showAllBtn, hideAllBtn, onToggle, onShowAll, onHideAll } = deps;

  const syncLegendPressed = (typeName: string, visible: boolean) => {
    const btn = _legendButtons.get(typeName);
    if (btn) btn.setAttribute("aria-pressed", visible ? "true" : "false");
  };

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
      cb.className = "filter-checkbox";
      cb.checked = true;
      _addListener(cb, "change", () => {
        onToggle(t.type, cb.checked);
        syncLegendPressed(t.type, cb.checked);
      });
      _typeCheckboxes.set(t.type, cb);

      const chip = document.createElement("span");
      chip.className = "chip";
      applyTypeColor(chip, t.color);

      label.appendChild(cb);
      label.appendChild(chip);
      const textWrap = document.createElement("span");
      textWrap.className = "filter-item-text";
      textWrap.textContent = `${t.type} `;
      const countWrap = document.createElement("span");
      countWrap.className = "filter-item-count";
      countWrap.textContent = `(${t.count})`;
      textWrap.appendChild(countWrap);
      label.appendChild(textWrap);
      filtersRoot.appendChild(label);

      // Legend item: [color dot] [type name] [count] — the color identifier row.
      const legendItem = document.createElement("div");
      legendItem.className = "legend-item";
      const legendBtn = document.createElement("button");
      legendBtn.type = "button";
      legendBtn.setAttribute("aria-pressed", "true");
      legendBtn.title = `Toggle ${t.type} visibility`;
      const legendChip = document.createElement("span");
      legendChip.className = "chip";
      legendChip.setAttribute("aria-hidden", "true");
      applyTypeColor(legendChip, t.color);
      const legendLabel = document.createElement("span");
      legendLabel.className = "legend-label";
      legendLabel.textContent = t.type;
      const legendCount = document.createElement("span");
      legendCount.className = "legend-count";
      legendCount.textContent = String(t.count);
      legendBtn.appendChild(legendChip);
      legendBtn.appendChild(legendLabel);
      legendBtn.appendChild(legendCount);
      _legendButtons.set(t.type, legendBtn);
      _addListener(legendBtn, "click", () => {
        // Toggle: if type is currently hidden, show it; if shown, hide it.
        // The onToggle callback handles the hiddenTypes Set.
        const currentCb = _typeCheckboxes.get(t.type);
        const isCurrentlyHidden = currentCb ? !currentCb.checked : false;
        onToggle(t.type, isCurrentlyHidden);
        if (currentCb) currentCb.checked = isCurrentlyHidden;
        syncLegendPressed(t.type, isCurrentlyHidden);
      });
      legendItem.appendChild(legendBtn);
      legendRoot.appendChild(legendItem);
    });
  });

  if (deps.semanticClusterRoot && Array.isArray(deps.semanticClusters)) {
    deps.semanticClusters.forEach((cluster) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "semantic-cluster-filter-item";
      item.setAttribute("aria-pressed", "true");
      item.dataset.clusterStatus = cluster.status || "confirmed";
      const count = Array.isArray(cluster.member_node_ids) ? cluster.member_node_ids.length : 0;
      item.textContent = `${cluster.name} · ${cluster.status || "confirmed"} · ${count}`;
      deps.semanticClusterRoot.appendChild(item);
    });
  }

  // ── Show-all / Hide-all button wiring ─────────────────────────────────────
  if (showAllBtn) {
    _addListener(showAllBtn, "click", () => {
      _typeCheckboxes.forEach((cb, typeName) => {
        cb.checked = true;
        syncLegendPressed(typeName, true);
      });
      if (typeof onShowAll === "function") onShowAll();
    });
  }

  if (hideAllBtn) {
    _addListener(hideAllBtn, "click", () => {
      _typeCheckboxes.forEach((cb, typeName) => {
        cb.checked = false;
        onToggle(typeName, false);
        syncLegendPressed(typeName, false);
      });
      if (typeof onHideAll === "function") onHideAll();
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
  _legendButtons.forEach((btn) => { btn.setAttribute("aria-pressed", checked ? "true" : "false"); });
}

export function setTypeEnabled(typeName: string, enabled: boolean): void {
  const checkbox = _typeCheckboxes.get(typeName);
  if (checkbox) checkbox.checked = enabled;
  const button = _legendButtons.get(typeName);
  if (button) button.setAttribute("aria-pressed", enabled ? "true" : "false");
  if (_deps) _deps.onToggle(typeName, enabled);
}

/**
 * unmount — remove all event listeners and clear module state.
 */
export function unmount(): void {
  _listeners.forEach(({ el, type, fn }) => el.removeEventListener(type, fn));
  _listeners = [];
  _deps = null;
  _typeCheckboxes = new Map();
  _legendButtons = new Map();
}
