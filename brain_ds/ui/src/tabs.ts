// @ts-nocheck
// tabs.ts — Functional graph-level tab manager (ADR-008/009 compliant).
//
// Architecture: URL-navigation model.
//   - Switching tabs navigates to /?graph_id=<id>, which the server renders the
//     viewer for that graph. This is the simplest robust option — no client-side
//     graph swap, no vis.Network reinit, no event-handler rewiring.
//   - Tab state (open tab ids + active id) persists in sessionStorage so reloads
//     restore the tab strip.
//   - The "+" button fetches GET /api/graphs for the available graph list and
//     shows a dropdown; selecting one opens it as a new tab.
//
// Mount/unmount pattern matches split-pane.ts and workspace-chrome.ts.

export interface TabsDeps {
  /** Currently active graph id (from RENDER_CONTEXT.meta.graph_id) */
  activeGraphId: string;
  /** Label for the active graph (from RENDER_CONTEXT.meta.org) */
  activeGraphLabel: string;
  /** Motion preference */
  motionEnabled?: () => boolean;
}

import * as workspaceState from './workspace-state';

// ── Session state ──────────────────────────────────────────────────────────────

const SESSION_KEY = 'brain_ds.tabs';

interface TabEntry {
  id: string;
  label: string;
}

interface TabsState {
  tabs: TabEntry[];
  activeId: string;
}

function loadState(activeId: string, activeLabel: string): TabsState {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) {
      const parsed: TabsState = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.tabs) && parsed.tabs.length > 0) {
        // Ensure the current graph is represented
        const has = parsed.tabs.some((t) => t.id === activeId);
        if (!has) {
          parsed.tabs.push({ id: activeId, label: activeLabel });
        }
        parsed.activeId = activeId;
        return parsed;
      }
    }
  } catch (_e) {
    // Ignore storage errors
  }
  return { tabs: [{ id: activeId, label: activeLabel }], activeId };
}

function saveState(state: TabsState): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
  } catch (_e) {
    // Ignore storage errors
  }
}

// ── Module state ───────────────────────────────────────────────────────────────

let _state: TabsState | null = null;
let _stripEl: HTMLElement | null = null;
let _deps: TabsDeps | null = null;
let _listeners: Array<{
  target: EventTarget;
  type: string;
  handler: EventListenerOrEventListenerObject;
  options?: boolean | AddEventListenerOptions;
}> = [];
let _dropdownEl: HTMLElement | null = null;
let _newTabBtn: HTMLButtonElement | null = null;

// ── DOM helpers ────────────────────────────────────────────────────────────────

function makeTabItem(entry: TabEntry, isActive: boolean, isOnly: boolean): HTMLElement {
  const item = document.createElement('div');
  item.className = 'tab-item';
  item.setAttribute('data-tab-id', `tab-${entry.id}`);
  item.setAttribute('data-tab-active', String(isActive));

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'tab';
  btn.setAttribute('role', 'tab');
  btn.id = `tab-${entry.id}`;
  btn.setAttribute('aria-selected', String(isActive));
  btn.setAttribute('aria-controls', 'canvas-area');
  btn.setAttribute('tabindex', isActive ? '0' : '-1');
  btn.setAttribute('data-graph-id', entry.id);

  const icon = document.createElement('svg');
  icon.className = 'tab-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.setAttribute('width', '14');
  icon.setAttribute('height', '14');
  icon.innerHTML = '<use href="#icon-network"/>';
  btn.appendChild(icon);

  const label = document.createElement('span');
  label.className = 'tab-label';
  label.textContent = entry.label;
  btn.appendChild(label);

  item.appendChild(btn);

  // Close button
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'tab-close';
  close.setAttribute('aria-label', `Close tab ${entry.label}`);
  close.setAttribute('tabindex', '-1');
  close.setAttribute('data-tab-close-for', `tab-${entry.id}`);
  // Never the last tab — disable/hide × when only one tab remains
  if (isOnly) {
    close.setAttribute('disabled', '');
    close.setAttribute('aria-disabled', 'true');
    close.style.display = 'none';
  }
  const xSvg = document.createElement('svg');
  xSvg.setAttribute('aria-hidden', 'true');
  xSvg.setAttribute('width', '12');
  xSvg.setAttribute('height', '12');
  xSvg.innerHTML = '<use href="#icon-x"/>';
  close.appendChild(xSvg);
  item.appendChild(close);

  return item;
}

// ── Dropdown for graph picker ──────────────────────────────────────────────────

function closeDropdown(): void {
  if (_dropdownEl && _dropdownEl.parentNode) {
    _dropdownEl.parentNode.removeChild(_dropdownEl);
  }
  _dropdownEl = null;
  if (_newTabBtn) {
    _newTabBtn.setAttribute('aria-expanded', 'false');
  }
}

async function openGraphPicker(): Promise<void> {
  closeDropdown();
  if (!_newTabBtn || !_state) return;

  let graphs: Array<{ id: string; label: string }> = [];
  try {
    const res = await fetch('/api/graphs');
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data)) {
        graphs = data;
      }
    }
  } catch (_e) {
    // Fetch failed — show no graphs
  }

  // Filter out already-open tabs
  const openIds = new Set(_state.tabs.map((t) => t.id));
  const available = graphs.filter((g) => !openIds.has(g.id));

  const dropdown = document.createElement('div');
  dropdown.className = 'tab-graph-picker';
  dropdown.setAttribute('role', 'menu');
  dropdown.setAttribute('aria-label', 'Open graph in new tab');

  if (available.length === 0) {
    const msg = document.createElement('div');
    msg.className = 'tab-graph-picker-empty';
    msg.textContent = available.length === 0 && graphs.length === openIds.size
      ? 'Todos los grafos ya están abiertos'
      : 'No hay grafos disponibles';
    dropdown.appendChild(msg);
  } else {
    for (const g of available) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'tab-graph-picker-item';
      item.setAttribute('role', 'menuitem');
      item.textContent = g.label;
      item.addEventListener('click', () => {
        closeDropdown();
        openGraphInNewTab(g.id, g.label);
      });
      dropdown.appendChild(item);
    }
  }

  // Position below the + button
  const rect = _newTabBtn.getBoundingClientRect();
  dropdown.style.position = 'fixed';
  dropdown.style.top = `${rect.bottom + 4}px`;
  dropdown.style.left = `${rect.left}px`;
  dropdown.style.zIndex = '3000';

  document.body.appendChild(dropdown);
  _dropdownEl = dropdown;
  _newTabBtn.setAttribute('aria-expanded', 'true');

  // Focus first item
  const first = dropdown.querySelector('[role="menuitem"]') as HTMLElement | null;
  if (first) first.focus();

  // Keyboard nav inside dropdown
  const dropdownKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { closeDropdown(); _newTabBtn?.focus(); return; }
    if (!_dropdownEl) return;
    const items = Array.from(_dropdownEl.querySelectorAll('[role="menuitem"]')) as HTMLElement[];
    if (!items.length) return;
    const cur = Math.max(0, items.indexOf(document.activeElement as HTMLElement));
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(cur + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(cur - 1 + items.length) % items.length].focus(); }
  };
  dropdown.addEventListener('keydown', dropdownKeydown);
}

function openGraphInNewTab(graphId: string, label: string): void {
  if (!_state) return;
  workspaceState.capture(_state.activeId);
  // Add to open tabs if not already there
  if (!_state.tabs.some((t) => t.id === graphId)) {
    _state.tabs.push({ id: graphId, label });
  }
  _state.activeId = graphId;
  saveState(_state);
  // Navigate to that graph
  window.location.href = `/?graph_id=${encodeURIComponent(graphId)}`;
}

// ── Tab activation ─────────────────────────────────────────────────────────────

function activateTab(graphId: string): void {
  if (!_state || graphId === _state.activeId) return;
  workspaceState.capture(_state.activeId);
  _state.activeId = graphId;
  saveState(_state);
  window.location.href = `/?graph_id=${encodeURIComponent(graphId)}`;
}

function closeTab(graphId: string): void {
  if (!_state) return;
  // Never close the last tab
  if (_state.tabs.length <= 1) return;
  // Animate out (respect reduced motion: skip when prefers-reduced-motion is set)
  const motionOk = typeof _deps?.motionEnabled === 'function' ? _deps.motionEnabled() : true;
  const tabEl = _stripEl?.querySelector(`[data-tab-id="tab-${graphId}"]`) as HTMLElement | null;

  const doClose = () => {
    if (!_state) return;
    const idx = _state.tabs.findIndex((t) => t.id === graphId);
    if (idx === -1) return;
    _state.tabs.splice(idx, 1);
    // If closing the active tab, activate the neighbor
    if (_state.activeId === graphId) {
      const neighbor = _state.tabs[Math.min(idx, _state.tabs.length - 1)];
      if (neighbor) {
        workspaceState.capture(graphId);
        _state.activeId = neighbor.id;
        saveState(_state);
        window.location.href = `/?graph_id=${encodeURIComponent(neighbor.id)}`;
        return;
      }
    }
    saveState(_state);
    renderStrip();
  };

  if (motionOk && tabEl) {
    tabEl.style.transition = 'opacity 150ms ease, max-width 200ms ease 50ms';
    tabEl.style.opacity = '0';
    tabEl.style.maxWidth = '0';
    tabEl.style.overflow = 'hidden';
    setTimeout(doClose, 220);
  } else {
    doClose();
  }
}

// ── Render strip ───────────────────────────────────────────────────────────────

function renderStrip(): void {
  if (!_stripEl || !_state) return;
  // Remove existing tab items and the new-tab button
  while (_stripEl.firstChild) {
    _stripEl.removeChild(_stripEl.firstChild);
  }

  const isOnly = _state.tabs.length === 1;

  for (const entry of _state.tabs) {
    const isActive = entry.id === _state.activeId;
    const item = makeTabItem(entry, isActive, isOnly);
    _stripEl.appendChild(item);
  }

  // New-tab button
  const newTabBtn = document.createElement('button');
  newTabBtn.type = 'button';
  newTabBtn.className = 'tab-new';
  newTabBtn.setAttribute('aria-label', 'New tab — open another graph');
  newTabBtn.setAttribute('aria-haspopup', 'menu');
  newTabBtn.setAttribute('aria-expanded', 'false');
  newTabBtn.setAttribute('tabindex', '0');
  newTabBtn.innerHTML = '<svg aria-hidden="true" width="16" height="16"><use href="#icon-plus"/></svg>';
  _stripEl.appendChild(newTabBtn);
  _newTabBtn = newTabBtn;

  // Wire tab click and close handlers via delegation on the strip
}

// ── Event handlers ─────────────────────────────────────────────────────────────

function onStripClick(e: MouseEvent): void {
  const target = e.target as HTMLElement;

  // New-tab button
  const newBtn = target.closest('.tab-new') as HTMLElement | null;
  if (newBtn) {
    e.preventDefault();
    if (_dropdownEl) {
      closeDropdown();
    } else {
      openGraphPicker();
    }
    return;
  }

  // Close button — check before tab button (it's inside the tab item)
  const closeBtn = target.closest('.tab-close') as HTMLElement | null;
  if (closeBtn) {
    const forId = closeBtn.getAttribute('data-tab-close-for') || '';
    const graphId = forId.replace(/^tab-/, '');
    if (graphId) closeTab(graphId);
    return;
  }

  // Tab button
  const tabBtn = target.closest('[role="tab"]') as HTMLElement | null;
  if (tabBtn) {
    const graphId = tabBtn.getAttribute('data-graph-id');
    if (graphId) activateTab(graphId);
  }
}

function onStripKeydown(e: KeyboardEvent): void {
  if (!_state || !_stripEl) return;
  const tabs = _state.tabs;
  const activeIdx = tabs.findIndex((t) => t.id === _state!.activeId);

  // Ctrl+Tab / Ctrl+Shift+Tab cycle tabs (best-effort — browser may intercept)
  if (e.ctrlKey && e.key === 'Tab') {
    e.preventDefault();
    const delta = e.shiftKey ? -1 : 1;
    const next = tabs[(activeIdx + delta + tabs.length) % tabs.length];
    if (next && next.id !== _state.activeId) activateTab(next.id);
    return;
  }

  // Arrow keys within the tablist (WAI-ARIA APG)
  const focused = e.target as HTMLElement;
  const tabEl = focused.closest('[role="tab"]') as HTMLElement | null;
  if (!tabEl) return;
  const curId = tabEl.getAttribute('data-graph-id');
  const curIdx = tabs.findIndex((t) => t.id === curId);
  let nextIdx = -1;
  if (e.key === 'ArrowRight') { e.preventDefault(); nextIdx = (curIdx + 1) % tabs.length; }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); nextIdx = (curIdx - 1 + tabs.length) % tabs.length; }
  else if (e.key === 'Home') { e.preventDefault(); nextIdx = 0; }
  else if (e.key === 'End') { e.preventDefault(); nextIdx = tabs.length - 1; }
  if (nextIdx >= 0) {
    const targetBtn = _stripEl.querySelector(`[data-graph-id="${tabs[nextIdx].id}"]`) as HTMLElement | null;
    if (targetBtn) { targetBtn.focus(); }
  }

  // Middle-click close (AuxClick = button 1 on aux, but handled in onStripAuxClick)
}

function onStripAuxClick(e: MouseEvent): void {
  // Middle-click (button 1) closes a tab
  if (e.button !== 1) return;
  const tabBtn = (e.target as HTMLElement).closest('[role="tab"]') as HTMLElement | null;
  if (!tabBtn) return;
  e.preventDefault();
  const graphId = tabBtn.getAttribute('data-graph-id');
  if (graphId) closeTab(graphId);
}

function onDocumentKeydown(e: KeyboardEvent): void {
  // Global Ctrl+Tab / Ctrl+Shift+Tab
  if (!e.ctrlKey || e.key !== 'Tab') return;
  if (!_state || _state.tabs.length <= 1) return;
  e.preventDefault();
  const tabs = _state.tabs;
  const activeIdx = tabs.findIndex((t) => t.id === _state!.activeId);
  const delta = e.shiftKey ? -1 : 1;
  const next = tabs[(activeIdx + delta + tabs.length) % tabs.length];
  if (next && next.id !== _state.activeId) activateTab(next.id);
}

function onClickOutside(e: Event): void {
  if (!_dropdownEl) return;
  const t = e.target as Node | null;
  if (!t) return;
  if (_dropdownEl.contains(t)) return;
  if (_newTabBtn && _newTabBtn.contains(t)) return;
  closeDropdown();
}

// ── Public lifecycle ───────────────────────────────────────────────────────────

/**
 * mount — initialize the tab manager on the existing .tab-strip element.
 *
 * The mount call replaces the static hardcoded tab with a live-rendered strip.
 * It reads/writes sessionStorage for cross-navigation persistence.
 */
export function mount(
  stripEl: HTMLElement,
  deps: TabsDeps,
): { unmount: () => void } {
  if (!stripEl) return { unmount: () => {} };

  _stripEl = stripEl;
  _deps = deps;
  _state = loadState(deps.activeGraphId, deps.activeGraphLabel);

  renderStrip();

  const clickHandler = onStripClick.bind(null);
  const keydownHandler = onStripKeydown.bind(null);
  const auxClickHandler = onStripAuxClick.bind(null);
  const docKeydown = onDocumentKeydown.bind(null);
  const docPointerdown = onClickOutside.bind(null);

  stripEl.addEventListener('click', clickHandler);
  stripEl.addEventListener('keydown', keydownHandler);
  stripEl.addEventListener('auxclick', auxClickHandler);
  document.addEventListener('keydown', docKeydown);
  document.addEventListener('pointerdown', docPointerdown, true);

  _listeners = [
    { target: stripEl, type: 'click', handler: clickHandler },
    { target: stripEl, type: 'keydown', handler: keydownHandler },
    { target: stripEl, type: 'auxclick', handler: auxClickHandler },
    { target: document, type: 'keydown', handler: docKeydown },
    { target: document, type: 'pointerdown', handler: docPointerdown, options: true },
  ];

  return {
    unmount: () => {
      closeDropdown();
      _listeners.forEach(({ target, type, handler, options }) => {
        (target as any).removeEventListener(type, handler, options);
      });
      _listeners = [];
      _stripEl = null;
      _deps = null;
      _state = null;
      _newTabBtn = null;
    },
  };
}
