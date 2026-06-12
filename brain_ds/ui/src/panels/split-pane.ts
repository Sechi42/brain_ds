// @ts-nocheck

import { renderMarkdown } from './markdown-mini';

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeEntry {
  id: string;
  label?: string;
  sections?: Array<{ title?: string; content?: string }>;
  notes?: string;
  relationships?: {
    incoming?: Array<{ source_id?: string; source_label?: string; edge_label?: string }>;
    outgoing?: Array<{ target_id?: string; target_label?: string; edge_label?: string }>;
  };
}

export interface SplitPaneDeps {
  /** Markdown for a node. The reader passes the node it is SHOWING — never
   *  rely solely on the canvas selection, which can change or clear mid-edit. */
  getMarkdown?: (nodeId?: string | null) => string;
  saveMarkdown?: (markdown: string, nodeId?: string | null) => Promise<boolean>;
  hasSelection?: () => boolean;
  onRequireSelection?: () => void;
  /** Returns the currently selected node id */
  getSelectedNodeId?: () => string | null;
  /** Returns the full detail_index entry for a node id */
  getDetailEntry?: (nodeId: string) => NodeEntry | null;
  /** Returns all node entries (for backlink index) */
  getAllNodes?: () => NodeEntry[];
  /** Navigate the network to a node and open it in the reader */
  selectAndReveal?: (nodeId: string) => void;
  /** Resolve a wikilink target: returns nodeId or null */
  resolveWikilink?: (target: string) => string | null;
  /** Get graph id for API calls */
  getGraphId?: () => string;
  /** Motion preference */
  motionEnabled?: () => boolean;
}

// ── Backlink index ─────────────────────────────────────────────────────────────

interface BacklinkIndex {
  /** Map from nodeId → set of node ids that reference it */
  byNodeId: Map<string, Set<string>>;
  built: boolean;
  invalidatedFor: Set<string>;
}

const backlinkIndex: BacklinkIndex = {
  byNodeId: new Map(),
  built: false,
  invalidatedFor: new Set(),
};

function buildBacklinkIndex(allNodes: NodeEntry[]): void {
  backlinkIndex.byNodeId.clear();
  const wikilinkPattern = /\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g;
  for (const node of allNodes) {
    const texts: string[] = [];
    if (node.sections) {
      for (const s of node.sections) {
        if (s.content) texts.push(s.content);
      }
    }
    if (node.notes) texts.push(node.notes);
    const combined = texts.join('\n');
    let m: RegExpExecArray | null;
    while ((m = wikilinkPattern.exec(combined)) !== null) {
      const target = m[1].trim();
      if (!backlinkIndex.byNodeId.has(target)) backlinkIndex.byNodeId.set(target, new Set());
      backlinkIndex.byNodeId.get(target)!.add(node.id);
    }
  }
  backlinkIndex.built = true;
  backlinkIndex.invalidatedFor.clear();
}

function scheduleBacklinkBuild(getDeps: () => SplitPaneDeps): void {
  if (backlinkIndex.built) return;
  const task = () => {
    const deps = getDeps();
    if (typeof deps.getAllNodes === 'function') {
      buildBacklinkIndex(deps.getAllNodes());
    }
  };
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(task, { timeout: 2000 });
  } else {
    setTimeout(task, 100);
  }
}

function invalidateBacklinks(nodeId: string): void {
  backlinkIndex.invalidatedFor.add(nodeId);
}

// ── In-reader history stack ────────────────────────────────────────────────────

interface HistoryEntry {
  nodeId: string;
  scrollTop: number;
}

let _historyStack: HistoryEntry[] = [];
let _historyPointer = -1;

function historyPush(nodeId: string): void {
  // Drop forward history on new navigation
  _historyStack = _historyStack.slice(0, _historyPointer + 1);
  // Avoid duplicate consecutive entries
  if (_historyStack.length > 0 && _historyStack[_historyStack.length - 1].nodeId === nodeId) {
    return;
  }
  _historyStack.push({ nodeId, scrollTop: 0 });
  if (_historyStack.length > 50) _historyStack.shift();
  _historyPointer = _historyStack.length - 1;
}

function historyCanBack(): boolean {
  return _historyPointer > 0;
}

function historyBack(): string | null {
  if (!historyCanBack()) return null;
  _historyPointer--;
  return _historyStack[_historyPointer]?.nodeId ?? null;
}

function historyClear(): void {
  _historyStack = [];
  _historyPointer = -1;
}

// ── Module state ───────────────────────────────────────────────────────────────

let _root: HTMLElement | null = null;
let _deps: SplitPaneDeps = {};
let _previousLayout = 'collapsed';
let _lastTrigger: HTMLElement | null = null;
let _editing = false;
let _editingNotes = false;
let _currentNodeId: string | null = null;
let _getDepsRef: (() => SplitPaneDeps) | null = null;

// ── Wikilink resolution ────────────────────────────────────────────────────────

function resolveWikilink(target: string): string | null {
  if (typeof _deps.resolveWikilink === 'function') {
    return _deps.resolveWikilink(target);
  }
  return null;
}

function navigateToNode(nodeId: string): void {
  const reader = document.getElementById('markdown-reader');
  if (reader) {
    // Save current scroll position
    if (_currentNodeId && _historyPointer >= 0 && _historyStack[_historyPointer]) {
      _historyStack[_historyPointer].scrollTop = reader.scrollTop;
    }
  }
  historyPush(nodeId);
  _currentNodeId = nodeId;
  if (typeof _deps.selectAndReveal === 'function') {
    _deps.selectAndReveal(nodeId);
  }
  renderPreview();
}

// ── Render helpers ─────────────────────────────────────────────────────────────

function makeButton(id: string, label: string, onClick: () => void, extraClass = ''): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  if (id) btn.id = id;
  btn.className = `pill-btn btn-outline reader-btn${extraClass ? ' ' + extraClass : ''}`;
  btn.textContent = label;
  btn.addEventListener('click', onClick);
  return btn;
}

function createStatusSpan(): HTMLSpanElement {
  const s = document.createElement('span');
  s.className = 'reader-status';
  s.setAttribute('role', 'status');
  return s;
}

function flashStatus(el: HTMLSpanElement, message: string, duration = 2000): void {
  el.textContent = message;
  el.classList.add('is-visible');
  setTimeout(() => {
    el.classList.remove('is-visible');
    setTimeout(() => { if (!el.classList.contains('is-visible')) el.textContent = ''; }, 300);
  }, duration);
}

function renderWikilinks(html: string): string {
  // Replace [[target|alias]] and [[target]] with clickable spans
  return html.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, alias) => {
    const display = alias ? alias.trim() : target.trim();
    const resolvedId = resolveWikilink(target.trim());
    if (resolvedId) {
      return `<a class="wikilink" data-wikilink-target="${encodeURIComponent(resolvedId)}" href="#" aria-label="Navegar a ${display}">${display}</a>`;
    }
    return `<span class="wikilink wikilink--unresolved" title="Nodo no encontrado: ${target.trim()}">${display}</span>`;
  });
}

function getNotesForNode(nodeId: string): string {
  if (!nodeId) return '';
  const entry = typeof _deps.getDetailEntry === 'function' ? _deps.getDetailEntry(nodeId) : null;
  return (entry && entry.notes) ? entry.notes : '';
}

function getBacklinksForNode(nodeId: string): Array<{ id: string; label: string }> {
  if (!backlinkIndex.built) return [];
  const entry = typeof _deps.getDetailEntry === 'function' ? _deps.getDetailEntry(nodeId) : null;
  const label = entry?.label ?? nodeId;

  // Check by nodeId AND by label
  const referrers = new Set<string>();
  const byId = backlinkIndex.byNodeId.get(nodeId);
  if (byId) byId.forEach(id => referrers.add(id));
  // Also check label-based wikilinks
  const byLabel = backlinkIndex.byNodeId.get(label);
  if (byLabel) byLabel.forEach(id => referrers.add(id));

  return Array.from(referrers)
    .filter(id => id !== nodeId)
    .map(id => {
      const e = typeof _deps.getDetailEntry === 'function' ? _deps.getDetailEntry(id) : null;
      return { id, label: e?.label ?? id };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

function getEdgesForNode(nodeId: string): Array<{ label: string; relation: string }> {
  const entry = typeof _deps.getDetailEntry === 'function' ? _deps.getDetailEntry(nodeId) : null;
  if (!entry || !entry.relationships) return [];
  const result: Array<{ label: string; relation: string }> = [];
  for (const row of (entry.relationships.outgoing ?? [])) {
    result.push({ label: row.target_label ?? row.target_id ?? '', relation: `→ ${row.edge_label ?? 'relacionado'}` });
  }
  for (const row of (entry.relationships.incoming ?? [])) {
    result.push({ label: row.source_label ?? row.source_id ?? '', relation: `← ${row.edge_label ?? 'relacionado'}` });
  }
  return result;
}

// ── Save notes ─────────────────────────────────────────────────────────────────

async function saveNotes(nodeId: string, value: string): Promise<boolean> {
  const graphId = typeof _deps.getGraphId === 'function' ? _deps.getGraphId() : '';
  if (!graphId) return false;
  try {
    const response = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ graph_id: graphId, changes: { details: { notes: value } } }),
    });
    if (!response.ok) return false;
    // Update local cache
    const entry = typeof _deps.getDetailEntry === 'function' ? _deps.getDetailEntry(nodeId) : null;
    if (entry) entry.notes = value;
    // Invalidate backlinks for this node
    invalidateBacklinks(nodeId);
    // Rebuild index if already built
    if (backlinkIndex.built && _getDepsRef) {
      buildBacklinkIndex((_getDepsRef() as SplitPaneDeps).getAllNodes?.() ?? []);
    }
    return true;
  } catch (_e) {
    return false;
  }
}

// ── Main render ────────────────────────────────────────────────────────────────

function renderPreview(): void {
  const reader = document.getElementById('markdown-reader');
  if (!reader) return;
  _editing = false;
  _editingNotes = false;

  const nodeId = _currentNodeId ?? (typeof _deps.getSelectedNodeId === 'function' ? _deps.getSelectedNodeId() : null);
  const raw = typeof _deps.getMarkdown === 'function' ? _deps.getMarkdown(nodeId) : '';

  reader.innerHTML = '';

  // ── Toolbar ──────────────────────────────────────────────────────────────────
  const toolbar = document.createElement('div');
  toolbar.className = 'reader-toolbar';

  // Back button (history)
  if (historyCanBack()) {
    const backBtn = makeButton('', '← Volver', () => {
      const prevId = historyBack();
      if (prevId) {
        _currentNodeId = prevId;
        if (typeof _deps.selectAndReveal === 'function') _deps.selectAndReveal(prevId);
        renderPreview();
      }
    }, ' reader-btn--back');
    backBtn.title = 'Volver al nodo anterior (Alt+Izquierda)';
    toolbar.appendChild(backBtn);
  }

  // Edit content button — also offered when the node has no content yet, so
  // the user can create it from scratch ("Agregar contenido").
  if (typeof _deps.saveMarkdown === 'function' && nodeId) {
    toolbar.appendChild(makeButton('reader-edit', raw ? 'Editar' : 'Agregar contenido', () => {
      _editing = true;
      renderEditor(raw);
    }));
  }

  if (toolbar.childNodes.length) reader.appendChild(toolbar);

  // ── Content ───────────────────────────────────────────────────────────────────
  if (raw) {
    const content = document.createElement('div');
    content.className = 'reader-content';
    content.innerHTML = renderWikilinks(renderMarkdown(raw));
    reader.appendChild(content);
  } else {
    const empty = document.createElement('p');
    empty.style.cssText = 'color:var(--text-muted);padding:0.25rem 0;';
    empty.textContent = 'Sin contenido estructurado.';
    reader.appendChild(empty);
  }

  // ── Notes section ─────────────────────────────────────────────────────────────
  if (nodeId) {
    const notesSection = document.createElement('section');
    notesSection.className = 'reader-notes-section';
    notesSection.setAttribute('aria-label', 'Notas del nodo');

    const notesHeader = document.createElement('div');
    notesHeader.className = 'reader-notes-header';
    notesHeader.innerHTML = `<svg class="reader-notes-icon" aria-hidden="true" width="14" height="14"><use href="#icon-edit"/></svg><span>Notas</span>`;

    const notesStatus = createStatusSpan();
    notesStatus.className += ' reader-notes-status';
    notesHeader.appendChild(notesStatus);
    notesSection.appendChild(notesHeader);

    appendNotesView(nodeId, notesSection, notesStatus);
    reader.appendChild(notesSection);
  }

  // ── Backlinks / connections ────────────────────────────────────────────────────
  if (nodeId) {
    const connSection = document.createElement('section');
    connSection.className = 'reader-connections-section';
    connSection.setAttribute('aria-label', 'Conexiones del nodo');

    const connHeader = document.createElement('h4');
    connHeader.className = 'reader-connections-title';
    connHeader.innerHTML = `<svg aria-hidden="true" width="14" height="14"><use href="#icon-share-2"/></svg> Conexiones`;
    connSection.appendChild(connHeader);

    const edges = getEdgesForNode(nodeId);
    const backlinks = getBacklinksForNode(nodeId);

    if (!edges.length && !backlinks.length) {
      const none = document.createElement('p');
      none.className = 'reader-connections-empty';
      none.textContent = 'Sin conexiones o referencias.';
      connSection.appendChild(none);
    } else {
      const list = document.createElement('ul');
      list.className = 'reader-connections-list';

      for (const edge of edges) {
        const li = document.createElement('li');
        li.className = 'reader-connection-item reader-connection-item--edge';
        li.innerHTML = `<span class="reader-connection-relation">${edge.relation}</span> <span class="reader-connection-label">${edge.label}</span>`;
        list.appendChild(li);
      }

      for (const bl of backlinks) {
        const li = document.createElement('li');
        li.className = 'reader-connection-item reader-connection-item--backlink';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'reader-connection-link';
        btn.textContent = bl.label;
        btn.setAttribute('data-wikilink-target', encodeURIComponent(bl.id));
        btn.addEventListener('click', () => navigateToNode(bl.id));
        li.innerHTML = `<span class="reader-connection-relation">↩ menciona</span> `;
        li.appendChild(btn);
        list.appendChild(li);
      }

      connSection.appendChild(list);
    }

    reader.appendChild(connSection);
  }

  // ── Wikilink delegation — one listener on reader container ────────────────────
  // Already placed with event delegation at mount() time; no per-render listener.
  // Restore scroll position if navigating back
  const reader2 = document.getElementById('markdown-reader');
  if (reader2 && _historyPointer >= 0 && _historyStack[_historyPointer]) {
    const savedScroll = _historyStack[_historyPointer].scrollTop;
    if (savedScroll > 0) {
      requestAnimationFrame(() => { reader2.scrollTop = savedScroll; });
    } else {
      reader2.scrollTop = 0;
    }
  }
}

function appendNotesView(nodeId: string, container: HTMLElement, statusEl: HTMLSpanElement): void {
  const currentNotes = getNotesForNode(nodeId);
  const notesView = document.createElement('div');
  notesView.className = 'reader-notes-view';

  if (currentNotes) {
    notesView.innerHTML = renderWikilinks(renderMarkdown(currentNotes));
  } else {
    notesView.innerHTML = '<p class="reader-notes-empty">Sin notas. Hacé clic para agregar…</p>';
  }

  // Click on view to enter edit mode
  notesView.addEventListener('click', () => {
    showNotesEditor(nodeId, container, statusEl);
  });
  container.appendChild(notesView);
}

function showNotesEditor(nodeId: string, container: HTMLElement, statusEl: HTMLSpanElement): void {
  // Remove the view div, inject textarea
  const existing = container.querySelector('.reader-notes-view, .reader-notes-editor-wrap');
  if (existing) existing.remove();

  const wrap = document.createElement('div');
  wrap.className = 'reader-notes-editor-wrap';

  const textarea = document.createElement('textarea');
  textarea.className = 'reader-editor reader-notes-editor';
  textarea.setAttribute('aria-label', 'Notas del nodo (markdown)');
  textarea.value = getNotesForNode(nodeId);
  textarea.spellcheck = false;

  let _saveTimer: ReturnType<typeof setTimeout> | null = null;
  let _saving = false;

  const doSave = async () => {
    if (_saving) return;
    _saving = true;
    flashStatus(statusEl, 'Guardando…', 800);
    const ok = await saveNotes(nodeId, textarea.value);
    _saving = false;
    if (ok) {
      flashStatus(statusEl, 'Guardado ✓');
    } else {
      flashStatus(statusEl, 'Error al guardar', 3000);
    }
    return ok;
  };

  // Swap the editor back to the read view IN PLACE. Never re-render the whole
  // reader here: blur fires when the user clicks anywhere else (another node,
  // the canvas), and a full renderPreview() would follow the new selection —
  // the reader would jump away mid-save and look like the node lost its data.
  const closeEditor = () => {
    _editingNotes = false;
    if (!container.isConnected) return; // reader already re-rendered elsewhere
    const editorWrap = container.querySelector('.reader-notes-editor-wrap');
    if (editorWrap) editorWrap.remove();
    appendNotesView(nodeId, container, statusEl);
  };

  // Autosave on blur — skip the network round-trip when nothing changed.
  textarea.addEventListener('blur', () => {
    if (_saveTimer) clearTimeout(_saveTimer);
    if (textarea.value === getNotesForNode(nodeId)) {
      closeEditor();
      return;
    }
    doSave().then(() => closeEditor());
  });

  // Ctrl/Cmd+S saves without leaving
  textarea.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      if (_saveTimer) clearTimeout(_saveTimer);
      doSave();
    }
    if (e.key === 'Escape') {
      e.stopPropagation();
      textarea.blur();
    }
  });

  wrap.appendChild(textarea);
  container.appendChild(wrap);
  textarea.focus();
  _editingNotes = true;
}

function renderEditor(raw: string): void {
  const reader = document.getElementById('markdown-reader');
  if (!reader) return;
  _editing = true;
  reader.innerHTML = '';

  const toolbar = document.createElement('div');
  toolbar.className = 'reader-toolbar';
  const status = createStatusSpan();

  const textarea = document.createElement('textarea');
  textarea.className = 'reader-editor';
  textarea.id = 'reader-editor';
  textarea.value = raw;
  textarea.setAttribute('aria-label', 'Editor de markdown del nodo');
  textarea.spellcheck = false;

  // Pin the node being edited NOW: the canvas selection can change or clear
  // while the editor is open, and the save must still target this node.
  const editingNodeId = _currentNodeId
    ?? (typeof _deps.getSelectedNodeId === 'function' ? _deps.getSelectedNodeId() : null);

  const saveBtn = makeButton('reader-save', 'Guardar', async () => {
    saveBtn.disabled = true;
    flashStatus(status, 'Guardando…', 800);
    let ok = false;
    try {
      ok = await _deps.saveMarkdown(textarea.value, editingNodeId);
    } catch (_e) {
      ok = false;
    }
    saveBtn.disabled = false;
    if (ok) {
      flashStatus(status, 'Guardado ✓');
      setTimeout(() => renderPreview(), 400);
    } else {
      flashStatus(status, 'Error al guardar', 3000);
    }
  });

  textarea.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      saveBtn.click();
    }
  });

  toolbar.appendChild(saveBtn);
  toolbar.appendChild(makeButton('reader-cancel', 'Cancelar', () => renderPreview()));
  toolbar.appendChild(status);

  reader.appendChild(toolbar);
  reader.appendChild(textarea);
  textarea.focus();
}

// ── Show/hide ──────────────────────────────────────────────────────────────────

function show(): void {
  if (!_root) return;
  const current = _root.getAttribute('data-layout') || 'collapsed';
  if (current !== 'reader') _previousLayout = current;
  _root.setAttribute('data-layout', 'reader');

  const nodeId = typeof _deps.getSelectedNodeId === 'function' ? _deps.getSelectedNodeId() : null;
  if (nodeId) {
    historyPush(nodeId);
    _currentNodeId = nodeId;
  }
  renderPreview();

  const reader = document.getElementById('markdown-reader');
  if (reader) {
    reader.setAttribute('tabindex', '-1');
    reader.scrollTop = 0;
    (reader as HTMLElement).focus?.();
  }
}

function hide(): void {
  _editing = false;
  _editingNotes = false;
  if (!_root) return;
  _root.setAttribute('data-layout', _previousLayout === 'reader' ? 'collapsed' : _previousLayout);
  if (_lastTrigger && typeof _lastTrigger.focus === 'function') _lastTrigger.focus();
}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────────

function onKeydown(event: KeyboardEvent): void {
  if (!_root) return;
  const isReader = _root.getAttribute('data-layout') === 'reader';

  // Alt+Left — reader back navigation
  if (isReader && event.altKey && event.key === 'ArrowLeft') {
    event.preventDefault();
    if (historyCanBack()) {
      const prevId = historyBack();
      if (prevId) {
        _currentNodeId = prevId;
        if (typeof _deps.selectAndReveal === 'function') _deps.selectAndReveal(prevId);
        renderPreview();
      }
    }
    return;
  }

  if (event.key === 'Escape' && isReader) {
    event.preventDefault();
    if (_editing) { renderPreview(); return; }
    if (_editingNotes) { renderPreview(); return; }
    hide();
  }
}

// ── Wikilink delegation handler ────────────────────────────────────────────────

function onReaderClick(event: MouseEvent): void {
  const target = event.target as HTMLElement;
  const link = target.closest('[data-wikilink-target]') as HTMLElement | null;
  if (!link) return;
  event.preventDefault();
  const encodedId = link.getAttribute('data-wikilink-target') || '';
  const nodeId = decodeURIComponent(encodedId);
  if (nodeId) navigateToNode(nodeId);
}

// ── Public lifecycle ───────────────────────────────────────────────────────────

export function mount(
  root: HTMLElement,
  deps: SplitPaneDeps = {},
): { unmount: () => void; refreshForNode: (nodeId: string) => void } {
  if (!root) return { unmount: () => {}, refreshForNode: () => {} };

  _root = root;
  _deps = deps;
  _previousLayout = root.getAttribute('data-layout') || 'collapsed';
  _currentNodeId = null;
  historyClear();
  _getDepsRef = () => _deps;

  const showBtn = document.getElementById('show-more');
  const hideBtn = document.getElementById('hide-markdown');
  const reader = document.getElementById('markdown-reader');

  // Delegate wikilink clicks at the reader container level (single listener)
  if (reader) {
    reader.addEventListener('click', onReaderClick);
  }

  // Schedule backlink index build on idle
  scheduleBacklinkBuild(() => _deps);

  const onShowClick = (event: Event) => {
    _lastTrigger = (event.currentTarget as HTMLElement) || showBtn as HTMLElement;
    if (_root!.getAttribute('data-layout') === 'reader') {
      hide();
      return;
    }
    if (typeof deps.hasSelection === 'function' && !deps.hasSelection()) {
      if (typeof deps.onRequireSelection === 'function') deps.onRequireSelection();
      return;
    }
    show();
  };

  showBtn?.addEventListener('click', onShowClick);
  hideBtn?.addEventListener('click', hide);
  document.addEventListener('keydown', onKeydown);

  /**
   * refreshForNode — called externally when the active node changes while the
   * reader is open, so the reader stays in sync without closing/reopening.
   */
  const refreshForNode = (nodeId: string) => {
    if (_root!.getAttribute('data-layout') !== 'reader') return;
    if (nodeId === _currentNodeId) return;
    historyPush(nodeId);
    _currentNodeId = nodeId;
    renderPreview();
  };

  return {
    unmount: () => {
      showBtn?.removeEventListener('click', onShowClick);
      hideBtn?.removeEventListener('click', hide);
      document.removeEventListener('keydown', onKeydown);
      if (reader) reader.removeEventListener('click', onReaderClick);
      _root = null;
      _deps = {};
      _currentNodeId = null;
      historyClear();
      _getDepsRef = null;
    },
    refreshForNode,
  };
}
