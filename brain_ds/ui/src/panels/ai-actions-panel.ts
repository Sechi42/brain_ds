// panels/ai-actions-panel.ts — lazy per-node AI actions panel for Acciones IA tab.
//
// B4 design rules (NON-NEGOTIABLE):
// - Fetch ONLY on ai-actions tab reveal, for the currently selected node.
// - NEVER fetch in graph render path or on every node selection click.
// - Per-node cache (Map<nodeId, result>) + in-flight guard (Set<nodeId>).
// - Results render into #ai-actions-node-intel (NOT #ai-actions-receipts — that
//   belongs to the GII agent-activity feed per reconciliation decision 2508).
// - Loading / populated / empty / error states.
// - Non-blocking: fetch is async, graph stays interactive.
//
// Reconciliation constraint (LOCKED):
// - #ai-actions-receipts is NOT touched by this module.
// - B4 owns ONLY #ai-actions-node-intel.

export interface AiActionsPanelOptions {
  /** Graph ID used for API queries. */
  graphId: string;
  /** Base URL of the API server (default: "" = same origin). */
  apiBase?: string;
}

export interface AiActionsPanelHandle {
  /** Notify the panel which node is currently selected. */
  setSelectedNodeId(nodeId: string | null): void;
  /** Trigger a lazy fetch if the tab is open and the node is set. */
  onReveal(): void;
  /** Destroy the panel and clean up. */
  destroy(): void;
}

interface SuggestionsResult {
  node_id: string;
  suggestions: Array<{
    node_id: string;
    label?: string;
    type?: string;
    score: number;
    reason?: string;
  }>;
  total_candidates?: number;
  [key: string]: unknown;
}

interface CompletenessResult {
  graph_id: string;
  completeness_matrix: Record<string, string>;
  missing_for_brd: string[];
  underspecified_nodes: string[];
  missing_count: number;
  pre_mapping_recommendation: string;
  recommendation_detail: string;
  [key: string]: unknown;
}

interface CachedResult {
  suggestions: SuggestionsResult | null;
  completeness: CompletenessResult | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Module-level state (singleton per page load — mirrors pipeline-panel pattern)
// ---------------------------------------------------------------------------

let _panelEl: HTMLElement | null = null;
let _opts: AiActionsPanelOptions | null = null;
let _selectedNodeId: string | null = null;
let _cache: Map<string, CachedResult> = new Map();
let _inFlight: Set<string> = new Set();
let _mounted = false;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function _getOrCreateNodeIntel(): HTMLElement | null {
  let el = document.getElementById("ai-actions-node-intel") as HTMLElement | null;
  if (!el && _panelEl) {
    el = document.createElement("div");
    el.id = "ai-actions-node-intel";
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-label", "Node AI analysis");
    el.className = "ai-actions-node-intel";
    _panelEl.appendChild(el);
  }
  return el;
}

function _renderLoading(el: HTMLElement, nodeId: string): void {
  el.innerHTML = `
    <div class="ai-actions-node-intel__loading" aria-busy="true" role="status">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ai-actions-node-intel__spinner">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      <span>Analizando nodo…</span>
    </div>`;
}

function _renderReady(el: HTMLElement): void {
  el.innerHTML = `
    <div class="ai-actions-node-intel__empty" role="status">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
      <span>Abrí Acciones IA para analizar el nodo seleccionado.</span>
    </div>`;
}

function _renderEmpty(el: HTMLElement): void {
  el.innerHTML = `
    <div class="ai-actions-node-intel__empty" role="status">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
      <span>Seleccioná un nodo en el lienzo para ver sus conexiones sugeridas y completitud.</span>
    </div>`;
}

function _renderNoNode(el: HTMLElement): void {
  el.innerHTML = `
    <div class="ai-actions-node-intel__empty" role="status">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
      <span>Seleccioná un nodo para ver las acciones IA disponibles.</span>
    </div>`;
}

function _renderError(el: HTMLElement, message: string): void {
  el.innerHTML = `
    <div class="ai-actions-node-intel__error" role="alert">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--status-danger)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>${_escHtml(message)}</span>
    </div>`;
}

function _escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function _scoreBar(score: number): string {
  const pct = Math.round(score * 100);
  return `<span class="ai-actions-node-intel__score-bar" title="${pct}% afinidad" aria-label="${pct}% afinidad">
    <span class="ai-actions-node-intel__score-bar-fill" style="width:${pct}%;"></span>
  </span>`;
}

function _renderPopulated(
  el: HTMLElement,
  suggestions: SuggestionsResult,
  completeness: CompletenessResult
): void {
  const items = suggestions.suggestions ?? [];
  const recommendation = completeness.pre_mapping_recommendation ?? "";
  const missing = completeness.missing_for_brd ?? [];
  const missingCount = completeness.missing_count ?? 0;

  const suggestionHtml =
    items.length === 0
      ? `<p class="ai-actions-node-intel__hint">No se encontraron conexiones candidatas.</p>`
      : `<ol class="ai-actions-node-intel__suggestions" aria-label="Conexiones sugeridas">
          ${items
            .map(
              (s, i) => `
            <li class="ai-actions-node-intel__suggestion-item">
              <span class="ai-actions-node-intel__suggestion-rank" aria-hidden="true">${i + 1}</span>
              <span class="ai-actions-node-intel__suggestion-label">${_escHtml(s.label ?? s.node_id)}</span>
              <span class="ai-actions-node-intel__suggestion-type">${_escHtml(s.type ?? "")}</span>
              ${_scoreBar(s.score)}
              ${s.reason ? `<span class="ai-actions-node-intel__suggestion-reason">${_escHtml(s.reason)}</span>` : ""}
            </li>`
            )
            .join("")}
        </ol>`;

  const completenessIcon =
    recommendation === "proceed_with_gaps"
      ? `<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--status-active)" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`
      : `<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--status-warn)" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;

  const completenessLabel =
    recommendation === "proceed_with_gaps"
      ? "Grafo completo"
      : recommendation === "document"
      ? `${missingCount > 0 ? missingCount + " tipos faltantes" : "Nodos subdetallados"}`
      : `${missingCount} tipo${missingCount !== 1 ? "s" : ""} faltante${missingCount !== 1 ? "s" : ""}`;

  el.innerHTML = `
    <section class="ai-actions-node-intel__section" aria-label="Conexiones sugeridas">
      <h4 class="ai-actions-node-intel__heading">
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
        Conexiones sugeridas
        <span class="ai-actions-node-intel__count">${items.length}</span>
      </h4>
      ${suggestionHtml}
    </section>
    <section class="ai-actions-node-intel__section ai-actions-node-intel__section--completeness" aria-label="Completitud del grafo">
      <h4 class="ai-actions-node-intel__heading">
        ${completenessIcon}
        Completitud del grafo
      </h4>
      <p class="ai-actions-node-intel__completeness-label">${_escHtml(completenessLabel)}</p>
      <p class="ai-actions-node-intel__completeness-detail">${_escHtml(completeness.recommendation_detail ?? "")}</p>
      ${missing.length > 0 ? `<ul class="ai-actions-node-intel__missing-list" aria-label="Tipos faltantes">
        ${missing.map(t => `<li class="ai-actions-node-intel__missing-item">${_escHtml(t)}</li>`).join("")}
      </ul>` : ""}
    </section>`;
}

// ---------------------------------------------------------------------------
// Core fetch logic
// ---------------------------------------------------------------------------

async function _fetchAndRender(nodeId: string): Promise<void> {
  if (!_opts || !nodeId) return;

  const el = _getOrCreateNodeIntel();
  if (!el) return;

  // Cache hit — render immediately, no fetch
  const cached = _cache.get(nodeId);
  if (cached) {
    if (cached.error) {
      _renderError(el, cached.error);
    } else if (cached.suggestions && cached.completeness) {
      _renderPopulated(el, cached.suggestions, cached.completeness);
    } else {
      _renderEmpty(el);
    }
    return;
  }

  // In-flight guard — noop if already fetching this node
  if (_inFlight.has(nodeId)) {
    return;
  }

  _inFlight.add(nodeId);
  _renderLoading(el, nodeId);

  const base = _opts.apiBase ?? "";
  const graphId = encodeURIComponent(_opts.graphId);
  const nId = encodeURIComponent(nodeId);

  try {
    // Parallel fetch — both routes at once; non-blocking for canvas
    const [sugResp, compResp] = await Promise.all([
      fetch(`${base}/api/ai/suggestions?graph_id=${graphId}&node_id=${nId}`),
      fetch(`${base}/api/ai/completeness?graph_id=${graphId}&node_id=${nId}`),
    ]);

    let suggestions: SuggestionsResult | null = null;
    let completeness: CompletenessResult | null = null;
    let errorMsg: string | null = null;

    if (sugResp.ok) {
      suggestions = (await sugResp.json()) as SuggestionsResult;
    } else {
      const body = await sugResp.json().catch(() => ({ detail: "Error desconocido" }));
      errorMsg = (body as { detail?: string }).detail ?? `Error ${sugResp.status}`;
    }

    if (compResp.ok) {
      completeness = (await compResp.json()) as CompletenessResult;
    } else if (!errorMsg) {
      const body = await compResp.json().catch(() => ({ detail: "Error desconocido" }));
      errorMsg = (body as { detail?: string }).detail ?? `Error ${compResp.status}`;
    }

    // Only cache and render if this node is still the selected one
    if (_selectedNodeId === nodeId) {
      if (errorMsg) {
        _cache.set(nodeId, { suggestions: null, completeness: null, error: errorMsg });
        _renderError(el, errorMsg);
      } else if (suggestions && completeness) {
        _cache.set(nodeId, { suggestions, completeness, error: null });
        _renderPopulated(el, suggestions, completeness);
      } else {
        _cache.set(nodeId, { suggestions: null, completeness: null, error: null });
        _renderEmpty(el);
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Error de red";
    if (_selectedNodeId === nodeId) {
      _cache.set(nodeId, { suggestions: null, completeness: null, error: msg });
      const el2 = _getOrCreateNodeIntel();
      if (el2) _renderError(el2, msg);
    }
  } finally {
    _inFlight.delete(nodeId);
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function mount(
  containerEl: HTMLElement,
  opts: AiActionsPanelOptions
): AiActionsPanelHandle {
  _panelEl = containerEl;
  _opts = opts;
  _mounted = true;
  _cache = new Map();
  _inFlight = new Set();
  _selectedNodeId = null;

  // Create the node-intel element inside the container now (so tests can
  // assert its presence immediately after mount).
  _getOrCreateNodeIntel();

  return {
    setSelectedNodeId(nodeId: string | null): void {
      if (nodeId === _selectedNodeId) return;
      // Invalidate cache for old node (keep only current; B4-R5)
      if (_selectedNodeId) {
        _cache.delete(_selectedNodeId);
      }
      _selectedNodeId = nodeId;
      // Reset display on node change without pretending a fetch is in-flight.
      // The actual loading state appears only after onReveal() starts the lazy fetch.
      const el = document.getElementById("ai-actions-node-intel") as HTMLElement | null;
      if (el && nodeId) {
        _renderReady(el);
      } else if (el) {
        _renderNoNode(el);
      }
    },

    onReveal(): void {
      if (!_selectedNodeId) {
        const el = _getOrCreateNodeIntel();
        if (el) _renderNoNode(el);
        return;
      }
      // Lazy: fetch only on reveal (B4-R1/R2)
      _fetchAndRender(_selectedNodeId);
    },

    destroy(): void {
      _panelEl = null;
      _opts = null;
      _mounted = false;
      _selectedNodeId = null;
      _cache.clear();
      _inFlight.clear();
    },
  };
}
