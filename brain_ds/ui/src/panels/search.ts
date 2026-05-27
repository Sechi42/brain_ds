// @ts-nocheck
/**
 * panels/search.ts
 *
 * Search input + floating dropdown results panel.
 * Design binding: §1.2 — mount(root, deps) / unmount() shape.
 * No React, no lifecycle library — vanilla TS function with teardown.
 *
 * PR 4: extraction + minimal search UX (REQ-GVP-6.1, 6.4, 6.8).
 * Logic ported verbatim from graph_viewer.html inline script (topMatches,
 * renderResults, input event handlers). New additions:
 *   - Leading search icon (inline SVG placeholder, no sprite yet)
 *   - Clear button (×) with aria-label="Clear search", hidden when empty
 *   - Zero-results message: "No nodes match '{query}'"
 *   - Esc: closes dropdown, clears input, returns focus to input, calls onClear
 *   - Enter: selects first result via onSelect
 *   - Arrow key navigation deferred (not yet in template baseline)
 *
 * Deps shape (passed from template via mount()):
 *   nodes: NodeItem[]              — all graph nodes (RENDER_CONTEXT.nodes)
 *   onSelect: (nodeId: string) => void  — called when user selects a result
 *   onClear: () => void            — called on Esc (resetHighlight + applyVisibility)
 */

// ── Types ──────────────────────────────────────────────────────────────────

export interface SearchNode {
  id: string;
  label: string;
  type: string;
}

export interface SearchDeps {
  nodes: SearchNode[];
  onSelect: (nodeId: string) => void;
  onClear: () => void;
}

// ── Module state ────────────────────────────────────────────────────────────

let _root: HTMLElement | null = null;
let _deps: SearchDeps | null = null;
let _inputEl: HTMLInputElement | null = null;
let _clearBtn: HTMLButtonElement | null = null;
let _resultsEl: HTMLElement | null = null;
let _listeners: Array<{ el: EventTarget; type: string; fn: EventListener }> = [];
let _activeIndex = -1;
let _activeItems: SearchNode[] = [];

// ── Helpers ─────────────────────────────────────────────────────────────────

function _addListener(el: EventTarget, type: string, fn: EventListener): void {
  el.addEventListener(type, fn);
  _listeners.push({ el, type, fn });
}

/**
 * topMatches — port from template inline script.
 * Returns up to 10 nodes matching query by label or id (case-insensitive).
 * Exact label matches sorted first, then alphabetical.
 */
function topMatches(q: string, allNodes: SearchNode[]): SearchNode[] {
  if (!q) return [];
  const query = q.toLowerCase();
  return allNodes
    .filter((n) => n.label.toLowerCase().includes(query) || n.id.toLowerCase().includes(query))
    .sort(
      (a, b) =>
        Number(!(a.label.toLowerCase() === query)) -
        Number(!(b.label.toLowerCase() === query)) ||
        a.label.localeCompare(b.label),
    )
    .slice(0, 10);
}

/**
 * renderResults — build dropdown list items.
 * Zero-results: shows "No nodes match '{query}'" message (REQ-GVP-6.4).
 * Non-zero: creates one <li><button> per result.
 */
function renderResults(items: SearchNode[], query: string): void {
  if (!_resultsEl || !_deps) return;
  _resultsEl.innerHTML = "";
  _activeIndex = -1;
  _activeItems = items.slice();
  if (_inputEl) _inputEl.setAttribute("aria-activedescendant", "");

  if (items.length === 0 && query.length > 0) {
    // REQ-GVP-6.4: zero-results state — "No nodes match '{query}'" in muted color/small font.
    const emptyLi = document.createElement("li");
    emptyLi.className = "search-empty";
    emptyLi.setAttribute("aria-live", "polite");
    emptyLi.className = "search-empty";
    emptyLi.textContent = `No nodes match "${query}"`;
    _resultsEl.appendChild(emptyLi);
    _resultsEl.classList.add("is-open");
    if (_inputEl) _inputEl.setAttribute("aria-expanded", "true");
    return;
  }

  if (items.length === 0) {
    _resultsEl.classList.remove("is-open");
    if (_inputEl) _inputEl.setAttribute("aria-expanded", "false");
    return;
  }

  items.forEach((item, idx) => {
    const li = document.createElement("li");
    li.id = `search-option-${idx}`;
    li.setAttribute("role", "option");
    li.className = "search-option";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `${item.label} (${item.type})`;
    btn.className = "search-option-btn";
    btn.addEventListener("click", () => {
      if (_deps) _deps.onSelect(item.id);
      if (_resultsEl) _resultsEl.innerHTML = "";
      if (_inputEl) _inputEl.value = "";
      if (_inputEl) {
        _inputEl.setAttribute("aria-expanded", "false");
        _inputEl.setAttribute("aria-activedescendant", "");
      }
      _resultsEl?.classList.remove("is-open");
      _updateClearBtn();
    });
    li.appendChild(btn);
    _resultsEl.appendChild(li);
  });

  _resultsEl.classList.add("is-open");
  if (_inputEl) _inputEl.setAttribute("aria-expanded", "true");
}

function _selectByIndex(idx: number): void {
  if (!_resultsEl || !_inputEl || !_deps || !_activeItems.length) return;
  const max = _activeItems.length - 1;
  _activeIndex = Math.max(0, Math.min(idx, max));
  const options = Array.from(_resultsEl.querySelectorAll("li.search-option"));
  options.forEach((opt, i) => {
    const active = i === _activeIndex;
    opt.classList.toggle("is-active", active);
    opt.setAttribute("aria-selected", active ? "true" : "false");
  });
  const activeId = `search-option-${_activeIndex}`;
  _inputEl.setAttribute("aria-activedescendant", activeId);
}

/**
 * _updateClearBtn — show/hide the clear button based on input emptiness.
 * REQ-GVP-6.1: clear button (×) appears when input is non-empty.
 */
function _updateClearBtn(): void {
  if (!_clearBtn || !_inputEl) return;
  if (_inputEl.value.length > 0) {
    _clearBtn.hidden = false;
  } else {
    _clearBtn.hidden = true;
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * mount — initialize the search panel.
 *
 * @param root - The <section class="search-group"> element (or any container).
 *               mount() looks inside root for #node-search and #search-results.
 *               It also injects the search icon and clear button via DOM manipulation.
 * @param deps - SearchDeps bag: { nodes, onSelect, onClear }
 */
export function mount(root: HTMLElement | null, deps: SearchDeps): void {
  if (!root) return;
  _root = root;
  _deps = deps;
  _listeners = [];

  // Locate existing DOM elements (created in template HTML).
  _inputEl = root.querySelector<HTMLInputElement>("#node-search") ||
    document.getElementById("node-search") as HTMLInputElement;
  _resultsEl = root.querySelector<HTMLElement>("#search-results") ||
    document.getElementById("search-results") as HTMLElement;

  if (!_inputEl || !_resultsEl) return;

  // ── Inject search icon + clear button wrapper ───────────────────────────
  // Wrap input in a relative-positioned container so icon/clear-btn can be
  // placed absolutely inside it (simple, no extra CSS class required).
  const label = root.querySelector<HTMLElement>('[for="node-search"]') ||
    document.querySelector<HTMLElement>('[for="node-search"]');

  // Only inject once (guard against double-mount)
  if (!root.querySelector(".search-input-wrap")) {
    const wrap = document.createElement("div");
    wrap.className = "search-input-wrap";
    wrap.className = "search-input-wrap";

    // Leading search icon (inline SVG placeholder — sprite pipeline is PR 9)
    const iconSpan = document.createElement("span");
    iconSpan.className = "search-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.innerHTML = '<svg class="search-icon-svg" aria-hidden="true"><use href="#icon-search"/></svg>';

    // Clear button (×) — REQ-GVP-6.1
    _clearBtn = document.createElement("button");
    _clearBtn.type = "button";
    _clearBtn.setAttribute("aria-label", "Clear search");
    _clearBtn.hidden = true;
    _clearBtn.className = "search-clear-btn";
    _clearBtn.innerHTML = '<svg class="search-clear-icon" aria-hidden="true"><use href="#icon-x"/></svg>';

    // Reparent input into the wrap
    const parent = _inputEl.parentNode;
    if (parent) parent.insertBefore(wrap, _inputEl);
    wrap.appendChild(iconSpan);
    wrap.appendChild(_inputEl);
    wrap.appendChild(_clearBtn);

    // Adjust input left padding to make room for the icon
    _inputEl.classList.add("search-input");

    // Clear button click handler
    _clearBtn.addEventListener("click", () => {
        if (_inputEl) {
          _inputEl.value = "";
          _inputEl.focus();
          _inputEl.setAttribute("aria-expanded", "false");
          _inputEl.setAttribute("aria-activedescendant", "");
        }
        if (_resultsEl) _resultsEl.innerHTML = "";
        _resultsEl?.classList.remove("is-open");
        _updateClearBtn();
      });
  } else {
    // Already wrapped — just re-acquire the clear button ref
    _clearBtn = root.querySelector<HTMLButtonElement>(".search-input-wrap button[aria-label='Clear search']") ||
      document.querySelector<HTMLButtonElement>(".search-input-wrap button[aria-label='Clear search']");
  }

  // ── Input event handlers ──────────────────────────────────────────────────

  _addListener(_inputEl, "input", () => {
    const q = _inputEl!.value.trim();
    renderResults(topMatches(q, _deps!.nodes), q);
    _updateClearBtn();
  });

  _addListener(_inputEl, "keydown", (event: KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      _selectByIndex(_activeIndex + 1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      _selectByIndex(_activeIndex - 1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const pick = _activeIndex >= 0 ? _activeItems[_activeIndex] : topMatches(_inputEl!.value.trim(), _deps!.nodes)[0];
      if (pick && _deps) _deps.onSelect(pick.id);
      if (_resultsEl) _resultsEl.innerHTML = "";
      _resultsEl?.classList.remove("is-open");
      if (_inputEl) {
        _inputEl.setAttribute("aria-expanded", "false");
        _inputEl.setAttribute("aria-activedescendant", "");
      }
    }
    if (event.key === "Escape") {
      event.preventDefault();
      if (_inputEl) {
        _inputEl.value = "";
        _inputEl.focus();
      }
      if (_resultsEl) _resultsEl.innerHTML = "";
      _resultsEl?.classList.remove("is-open");
      _updateClearBtn();
      if (_inputEl) {
        _inputEl.setAttribute("aria-expanded", "false");
        _inputEl.setAttribute("aria-activedescendant", "");
      }
      // REQ-GVP-6.8: call onClear so resetHighlight + applyVisibility run in template scope.
      if (_deps) _deps.onClear();
    }
  });

  _inputEl.setAttribute("role", "combobox");
  _inputEl.setAttribute("aria-autocomplete", "list");
  _inputEl.setAttribute("aria-expanded", "false");
  _inputEl.setAttribute("aria-controls", "search-results");
  _inputEl.setAttribute("aria-activedescendant", "");
  _resultsEl.setAttribute("role", "listbox");
}

/**
 * unmount — remove all event listeners and clear module state.
 */
export function unmount(): void {
  _listeners.forEach(({ el, type, fn }) => el.removeEventListener(type, fn));
  _listeners = [];
  _root = null;
  _deps = null;
  _inputEl = null;
  _clearBtn = null;
  _resultsEl = null;
}
