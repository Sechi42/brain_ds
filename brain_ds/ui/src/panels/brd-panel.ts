// @ts-nocheck
// panels/brd-panel.ts — BRD (Business Requirements Document) panel.
//
// Persistence convention:
//   A BRD is stored as a graph node with:
//     id      = "brd-{graphId}"
//     label   = "BRD"
//     type    = "Unknown"
//     card_sections[0].content = <markdown string>
//
//   This reuses the existing node PATCH /api/nodes infrastructure.
//   No new store tables or endpoints needed.
//
// Freshness: compare brd node's modified_at against max(modified_at) of all
//   other nodes in RENDER_CONTEXT — shows a chip: green "Actualizado" or amber
//   "Posiblemente desactualizado — N nodos cambiaron después".

import { renderMarkdown } from './markdown-mini';

// ── Types ──────────────────────────────────────────────────────────────────────

interface BrdPanelDeps {
  graphId: string;
  /** All node detail entries (keyed by node id). detail_index from RENDER_CONTEXT */
  detailIndex: Record<string, any>;
  /** All flat nodes from RENDER_CONTEXT.nodes (for modified_at comparison) */
  allNodes: Array<{ id: string; modified_at?: string }>;
  /** Resolve wikilink target → nodeId */
  resolveWikilink?: (target: string) => string | null;
  /** Navigate to node in graph + open reader */
  selectAndReveal?: (nodeId: string) => void;
}

// ── Module state ───────────────────────────────────────────────────────────────

let _deps: BrdPanelDeps | null = null;
let _panelEl: HTMLElement | null = null;
let _listeners: Array<{
  target: EventTarget;
  type: string;
  handler: EventListenerOrEventListenerObject;
  options?: boolean | AddEventListenerOptions;
}> = [];
let _brdContent = '';
let _brdModifiedAt = '';
let _otherNodes: Array<{ id: string; modified_at?: string }> = [];
let _editing = false;

// ── BRD node helpers ───────────────────────────────────────────────────────────

function brdNodeId(): string {
  return `brd-${_deps?.graphId ?? ''}`;
}

async function loadBrdFromServer(): Promise<void> {
  if (!_deps) return;
  try {
    const res = await fetch(`/api/nodes?graph_id=${encodeURIComponent(_deps.graphId)}`);
    if (!res.ok) return;
    const data = await res.json();
    const nodes: any[] = data.nodes ?? [];
    // Capture all non-BRD nodes for freshness comparison
    _otherNodes = nodes
      .filter((n: any) => n.id !== brdNodeId())
      .map((n: any) => ({ id: n.id, modified_at: n.modified_at }));
    const brd = nodes.find((n: any) => n.id === brdNodeId());
    if (brd) {
      const sections: any[] = brd.card_sections ?? [];
      const main = sections.find((s: any) => s.order === 0 || s.title === 'Contenido') ?? sections[0];
      _brdContent = main?.content ?? '';
      _brdModifiedAt = brd.modified_at ?? '';
    }
  } catch (_e) {
    // Ignore fetch errors
  }
}

async function saveBrd(markdown: string): Promise<boolean> {
  if (!_deps) return false;
  try {
    const res = await fetch(`/api/nodes/${encodeURIComponent(brdNodeId())}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        graph_id: _deps.graphId,
        changes: {
          label: 'BRD',
          type: 'Unknown',
          card_sections: [{ title: 'Contenido', content: markdown, order: 0, icon: '' }],
        },
      }),
    });
    if (!res.ok) return false;
    _brdContent = markdown;
    const refreshed = await res.json();
    _brdModifiedAt = refreshed?.node?.modified_at ?? _brdModifiedAt;
    return true;
  } catch (_e) {
    return false;
  }
}

async function createBrdNode(markdown: string): Promise<boolean> {
  if (!_deps) return false;
  try {
    const res = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        graph_id: _deps.graphId,
        node: {
          id: brdNodeId(),
          label: 'BRD',
          type: 'Unknown',
          card_sections: [{ title: 'Contenido', content: markdown, order: 0, icon: '' }],
        },
      }),
    });
    if (!res.ok) return false;
    _brdContent = markdown;
    return true;
  } catch (_e) {
    return false;
  }
}

// ── Wikilink rendering (mirrors split-pane.ts) ─────────────────────────────────

function renderWikilinks(html: string): string {
  const buildLink = (target: string, displayOverride?: string) => {
    const display = displayOverride ? displayOverride.trim() : target.trim();
    const resolvedId = _deps?.resolveWikilink ? _deps.resolveWikilink(target.trim()) : null;
    if (resolvedId) {
      return `<a class="wikilink" data-wikilink-target="${encodeURIComponent(resolvedId)}" href="#${encodeURIComponent(resolvedId)}" aria-label="Navegar a ${display}">${display}</a>`;
    }
    return `<span class="wikilink wikilink--unresolved" title="Nodo no encontrado: ${target.trim()}">${display}</span>`;
  };
  const withRawWikilinks = html.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, alias) => buildLink(target, alias));
  return withRawWikilinks.replace(/<a class="wikilink" data-node-label="([^"]+)">([^<]+)<\/a>/g, (_, target, display) => buildLink(target, display));
}

function onBrdPanelClick(e: MouseEvent): void {
  const t = e.target as HTMLElement;
  const link = t.closest('[data-wikilink-target]') as HTMLElement | null;
  if (!link) return;
  e.preventDefault();
  const nodeId = decodeURIComponent(link.getAttribute('data-wikilink-target') || '');
  if (nodeId && _deps?.selectAndReveal) {
    _deps.selectAndReveal(nodeId);
  }
}

// ── Freshness chip ─────────────────────────────────────────────────────────────

function computeFreshness(): { fresh: boolean; changedCount: number } {
  if (!_brdModifiedAt) return { fresh: true, changedCount: 0 };
  const brdTs = new Date(_brdModifiedAt).getTime();
  let count = 0;
  // Use server-fetched nodes if available (have modified_at), else deps.allNodes
  const nodesToCheck = _otherNodes.length > 0 ? _otherNodes : (_deps?.allNodes ?? []);
  for (const n of nodesToCheck) {
    if (n.id === brdNodeId()) continue;
    if (n.modified_at) {
      const ts = new Date(n.modified_at as string).getTime();
      if (ts > brdTs) count++;
    }
  }
  return { fresh: count === 0, changedCount: count };
}

// ── Status flash helper ────────────────────────────────────────────────────────

function flashStatus(el: HTMLElement, message: string, durationMs = 2200): void {
  el.textContent = message;
  el.classList.add('is-visible');
  setTimeout(() => {
    el.classList.remove('is-visible');
  }, durationMs);
}

// ── Render ─────────────────────────────────────────────────────────────────────

function renderPanel(): void {
  if (!_panelEl) return;
  _panelEl.innerHTML = '';
  _editing = false;

  // Header
  const header = document.createElement('div');
  header.className = 'brd-panel-header';

  const title = document.createElement('h3');
  title.className = 'brd-panel-title';
  title.innerHTML = `
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
    </svg>
    BRD
  `;
  header.appendChild(title);

  // Freshness chip (only if BRD exists)
  if (_brdContent) {
    const { fresh, changedCount } = computeFreshness();
    const chip = document.createElement('span');
    chip.className = `brd-freshness-chip ${fresh ? 'brd-freshness-chip--fresh' : 'brd-freshness-chip--stale'}`;
    chip.setAttribute('aria-live', 'polite');
    chip.textContent = fresh
      ? 'Actualizado'
      : `Posiblemente desactualizado — ${changedCount} nodo${changedCount !== 1 ? 's' : ''} cambiaron después`;
    header.appendChild(chip);
  }

  _panelEl.appendChild(header);

  if (!_brdContent) {
    // Empty state
    const empty = document.createElement('div');
    empty.className = 'brd-empty-state';
    empty.innerHTML = `
      <div class="brd-empty-icon">
        <svg aria-hidden="true" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
      </div>
      <p class="brd-empty-text">Aún no hay BRD.</p>
      <p class="brd-empty-hint">Generalo con <code>/generate-brd --save</code> desde tu agente.</p>
    `;
    // Allow creating a blank BRD from the UI too
    const createBtn = document.createElement('button');
    createBtn.type = 'button';
    createBtn.className = 'pill-btn btn-outline brd-create-btn';
    createBtn.textContent = 'Crear BRD vacío';
    createBtn.addEventListener('click', () => renderEditor(''));
    empty.appendChild(createBtn);
    _panelEl.appendChild(empty);
    return;
  }

  // Summary mode — the side panel shows metadata + a short preview only.
  // The full document opens in the center markdown reader (full width),
  // where viewing and editing have proper room.
  const summary = document.createElement('div');
  summary.className = 'brd-panel-summary';

  const statusMatch = _brdContent.match(/Status:\s*([A-ZÁÉÍÓÚ]+)/i);
  const orgMatch = _brdContent.match(/Organization:\s*(.+)/i);
  const sectionCount = (_brdContent.match(/^##\s+/gm) || []).length;

  const metaList = document.createElement('dl');
  metaList.className = 'brd-summary-meta';
  const metaPairs: Array<[string, string]> = [];
  const { fresh, changedCount } = computeFreshness();
  if (statusMatch) metaPairs.push(['Estado', statusMatch[1].toUpperCase()]);
  if (orgMatch) metaPairs.push(['Organización', orgMatch[1].trim()]);
  metaPairs.push(['Secciones', String(sectionCount)]);
  if (_brdModifiedAt) {
    const updatedLabel = new Date(_brdModifiedAt).toLocaleString();
    metaPairs.push(['Actualizado', updatedLabel]);
    metaPairs.push([
      'Frescura',
      fresh
        ? `Actualizado · ${updatedLabel}`
        : `Posiblemente desactualizado · ${updatedLabel} · ${changedCount} nodo${changedCount !== 1 ? 's' : ''} cambiaron después`,
    ]);
  }
  for (const [k, v] of metaPairs) {
    const dt = document.createElement('dt');
    dt.textContent = k;
    const dd = document.createElement('dd');
    if (k === 'Frescura') {
      const chip = document.createElement('span');
      chip.className = `brd-freshness-chip ${fresh ? 'brd-freshness-chip--fresh' : 'brd-freshness-chip--stale'}`;
      chip.setAttribute('aria-live', 'polite');
      chip.textContent = v;
      dd.appendChild(chip);
    } else {
      dd.textContent = v;
    }
    metaList.appendChild(dt);
    metaList.appendChild(dd);
  }
  summary.appendChild(metaList);

  const actions = document.createElement('div');
  actions.className = 'brd-panel-actions';
  const openBtn = document.createElement('button');
  openBtn.type = 'button';
  openBtn.className = 'pill-btn btn-outline brd-open-btn';
  openBtn.innerHTML = '<svg class="card-icon" aria-hidden="true" width="14" height="14"><use href="#icon-maximize"/></svg> Abrir BRD completo';
  openBtn.title = 'Ver y editar el BRD en el lector central';
  openBtn.addEventListener('click', () => openFullReader());
  actions.appendChild(openBtn);
  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'pill-btn btn-outline brd-edit-btn';
  editBtn.innerHTML = '<svg class="card-icon" aria-hidden="true" width="14" height="14"><use href="#icon-edit-3"/></svg> Editar';
  editBtn.title = 'Editar el BRD desde este panel';
  editBtn.addEventListener('click', () => renderEditor(_brdContent));
  actions.appendChild(editBtn);
  summary.appendChild(actions);

  // Short preview: executive summary (or first lines) so the side panel stays a resumen.
  const previewSource = extractPreview(_brdContent);
  if (previewSource) {
    const content = document.createElement('div');
    content.className = 'brd-panel-content brd-panel-content--preview reader-content';
    content.innerHTML = renderWikilinks(renderMarkdown(previewSource));
    summary.appendChild(content);
  }

  _panelEl.appendChild(summary);

  // Wikilink delegation
  _panelEl.addEventListener('click', onBrdPanelClick);
}

/** First meaningful chunk for the side-panel preview: the Executive Summary
 *  section when present, otherwise the first ~12 lines of the document. */
function extractPreview(markdown: string): string {
  const execMatch = markdown.match(/##\s+Executive Summary\s*\n([\s\S]*?)(?=\n##\s+|$)/i);
  if (execMatch && execMatch[1].trim()) {
    return `### Executive Summary\n\n${execMatch[1].trim()}`;
  }
  return markdown.split(/\r?\n/).slice(0, 12).join('\n');
}

/** Open the BRD node in the center markdown reader (full width view + edit).
 *  Mirrors the wikilink pattern: select the node, then open the reader pane. */
function openFullReader(): void {
  if (!_deps) return;
  try {
    if (_deps.selectAndReveal) _deps.selectAndReveal(brdNodeId());
  } catch (_e) {
    // Node not in the rendered network yet (created after page load without
    // live sync) — reload keeps things consistent.
    window.location.reload();
    return;
  }
  const split = document.getElementById('center-split');
  if (split && split.getAttribute('data-layout') === 'reader') return;
  const readerBtn = document.getElementById('show-more');
  if (readerBtn) (readerBtn as HTMLElement).click();
}

function renderEditor(initial: string): void {
  if (!_panelEl) return;
  _panelEl.innerHTML = '';
  _editing = true;

  const header = document.createElement('div');
  header.className = 'brd-panel-header';
  const title = document.createElement('h3');
  title.className = 'brd-panel-title';
  title.textContent = _brdContent ? 'Editar BRD' : 'Nuevo BRD';
  header.appendChild(title);
  _panelEl.appendChild(header);

  const statusEl = document.createElement('span');
  statusEl.className = 'reader-status';
  statusEl.setAttribute('role', 'status');

  const textarea = document.createElement('textarea');
  textarea.className = 'reader-editor brd-editor';
  textarea.setAttribute('aria-label', 'Editor BRD (markdown)');
  textarea.value = initial;
  textarea.spellcheck = false;

  let _saving = false;

  const doSave = async () => {
    if (_saving) return;
    _saving = true;
    flashStatus(statusEl, 'Guardando…', 800);
    const md = textarea.value;
    let ok = false;
    if (_brdContent) {
      ok = await saveBrd(md);
    } else {
      ok = await createBrdNode(md);
    }
    _saving = false;
    if (ok) {
      flashStatus(statusEl, 'Guardado ✓');
      setTimeout(() => renderPanel(), 400);
    } else {
      flashStatus(statusEl, 'Error al guardar', 3000);
    }
  };

  const toolbar = document.createElement('div');
  toolbar.className = 'reader-toolbar';

  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.className = 'pill-btn btn-outline reader-btn';
  saveBtn.innerHTML = '<svg class="card-icon" aria-hidden="true" width="14" height="14"><use href="#icon-save"/></svg> Guardar';
  saveBtn.addEventListener('click', doSave);

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'pill-btn btn-outline reader-btn';
  cancelBtn.textContent = 'Cancelar';
  cancelBtn.addEventListener('click', () => {
    _editing = false;
    renderPanel();
  });

  textarea.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      doSave();
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      if (!_editing) return;
      _editing = false;
      renderPanel();
    }
  });

  textarea.addEventListener('blur', () => {
    // Autosave only if content changed
    if (textarea.value !== initial) {
      doSave();
    }
  });

  toolbar.appendChild(saveBtn);
  toolbar.appendChild(cancelBtn);
  toolbar.appendChild(statusEl);

  _panelEl.appendChild(toolbar);
  _panelEl.appendChild(textarea);
  textarea.focus();
}

// ── Public lifecycle ───────────────────────────────────────────────────────────

/**
 * mount — attach the BRD panel to a container element.
 *
 * The panel loads BRD content from the server (GET /api/nodes) on mount,
 * then renders markdown with wikilink support.
 */
export async function mount(
  panelEl: HTMLElement,
  deps: BrdPanelDeps,
): Promise<{ unmount: () => void; refresh: () => Promise<void> }> {
  if (!panelEl) return { unmount: () => {}, refresh: async () => {} };

  _panelEl = panelEl;
  _deps = deps;
  _brdContent = '';
  _brdModifiedAt = '';
  _otherNodes = [];
  _editing = false;
  _listeners = [];

  // Check local detail_index first (avoids a round-trip if BRD was loaded in initial render)
  const brdEntry = deps.detailIndex?.[brdNodeId()];
  if (brdEntry) {
    const sections: any[] = brdEntry.sections ?? [];
    const main = sections.find((s: any) => s.order === 0 || s.title === 'Contenido') ?? sections[0];
    _brdContent = main?.content ?? '';
    // modified_at exposed via allNodes
    const brdNode = deps.allNodes?.find((n: any) => n.id === brdNodeId());
    _brdModifiedAt = brdNode?.modified_at ?? '';
  } else {
    // Not in initial render context — fetch from server
    await loadBrdFromServer();
  }

  renderPanel();

  return {
    unmount: () => {
      if (_panelEl) {
        _panelEl.removeEventListener('click', onBrdPanelClick);
      }
      _listeners.forEach(({ target, type, handler, options }) => {
        (target as any).removeEventListener(type, handler, options);
      });
      _listeners = [];
      _panelEl = null;
      _deps = null;
    },
    refresh: async () => {
      await loadBrdFromServer();
      renderPanel();
    },
  };
}
