// @ts-nocheck
/**
 * panels/detail-panel.ts
 *
 * Right-side node detail card. Subscribes to "select-change".
 * Design binding: §1.2 — mount(root, deps) / unmount() shape.
 * No React, no lifecycle library — vanilla TS function with teardown.
 *
 * PR 3: extraction-only. Zero new visual behaviour vs. graph_viewer.html baseline.
 * All DOM construction logic is moved verbatim from the template inline script.
 *
 * Deps shape (passed from template via mount()):
 *   editedDetailIndex: Record<string, DetailEntry>
 *   editedData: { nodes: NodeItem[] }
 *   network: vis.Network-like with .on(), .selectedNodeIds, .clearSelection(), etc.
 *   originalNodes: Map<string, NodeItem>
 *   RENDER_CONTEXT: { nodes, edges }
 *   adjacency: Record<string, string[]>
 *   motionEnabled: () => boolean
 */

// ── Types ──────────────────────────────────────────────────────────────────

export interface NodeItem {
  id: string;
  label: string;
  type: string;
  supertype: string;
  color?: string;
  editable_fields?: string[];
}

export interface EvidenceItem {
  id: string;
  content?: string;
  type?: string;
  source?: string;
  provenance?: unknown;
}

export interface RelationshipRow {
  source_id?: string;
  source_label?: string;
  target_id?: string;
  target_label?: string;
  edge_label?: string;
  reasons?: string[];
  evidence_ids?: string[];
}

export interface Relationships {
  incoming?: RelationshipRow[];
  outgoing?: RelationshipRow[];
}

export interface Section {
  title?: string;
  content?: string;
  icon?: string;
  accent_color?: string;
  is_gap?: boolean;
}

export interface DetailEntry {
  node: NodeItem;
  sections?: Section[];
  evidence?: EvidenceItem[];
  relationships?: Relationships;
}

export interface DetailPanelDeps {
  editedDetailIndex: Record<string, DetailEntry>;
  editedData: { nodes: NodeItem[] };
  network: {
    on(event: string, handler: (params: unknown) => void): void;
    selectedNodeIds: Set<string>;
    clearSelection(): void;
  };
  originalNodes: Map<string, NodeItem>;
  RENDER_CONTEXT: { nodes: NodeItem[]; edges: unknown[] };
  adjacency: Record<string, string[]>;
  motionEnabled: () => boolean;
}

// ── Module-level state (set by mount, cleared by unmount) ──────────────────

let _root: Element | null = null;
let _deps: DetailPanelDeps | null = null;
let _listeners: Array<{ el: Element; type: string; fn: EventListenerOrEventListenerObject }> = [];

// Cached DOM refs (set in mount)
let _detailPanel: Element | null = null;
let _detailTitle: Element | null = null;
let _detailMeta: Element | null = null;
let _detailBody: Element | null = null;
let _editToggleBtn: HTMLButtonElement | null = null;
let _exportJsonBtn: HTMLButtonElement | null = null;
let _detailSaveBtn: HTMLButtonElement | null = null;
let _detailCollapseBtn: HTMLButtonElement | null = null;

// Edit state (lives inside the mounted panel instance)
let _editMode = false;
let _selectedNodeId: string | null = null;
let _hasEdits = false;

const arrow = { incoming: "←", outgoing: "→" };

// ── Helpers ────────────────────────────────────────────────────────────────

function _on(el: Element, type: string, fn: EventListenerOrEventListenerObject): void {
  el.addEventListener(type, fn);
  _listeners.push({ el, type, fn });
}

function normalizeFieldName(value: unknown): string {
  return String(value ?? "").trim().toLowerCase().replace(/\s+/g, "_");
}

function isFieldEditable(node: NodeItem | undefined | null, fieldName: string): boolean {
  const fallbackEditableFields = new Set(["label", "details", "card_sections", "cards", "sections"]);
  const normalizedField = normalizeFieldName(fieldName);
  const editableFields = Array.isArray(node?.editable_fields)
    ? (node.editable_fields as string[]).map(normalizeFieldName).filter(Boolean)
    : [];
  if (editableFields.length) return editableFields.includes(normalizedField);
  return (
    fallbackEditableFields.has(normalizedField) ||
    normalizedField.startsWith("details") ||
    normalizedField.startsWith("card")
  );
}

function getEditedNode(nodeId: string): NodeItem | null {
  if (!_deps) return null;
  return (_deps.editedData.nodes ?? []).find((n) => n.id === nodeId) ?? null;
}

function toggleEditControls(): void {
  if (!_editToggleBtn || !_exportJsonBtn) return;
  const hasSelection = _selectedNodeId !== null;
  _editToggleBtn.hidden = !hasSelection;
  _exportJsonBtn.hidden = !_hasEdits;
  if (_detailSaveBtn) {
    _detailSaveBtn.hidden = !(_editMode && _hasEdits && hasSelection);
  }
}

function _graphId(): string {
  const api = (window as unknown as { brainDsUI?: { graphId?: string } }).brainDsUI;
  return String(api?.graphId || "");
}

function _clearConflictStale(): void {
  const parent = _detailBody?.parentElement;
  if (parent) parent.removeAttribute("data-conflict");
  const banner = document.getElementById("detail-conflict-banner");
  if (banner) banner.setAttribute("hidden", "true");
}

function _markConflictStale(): void {
  const parent = _detailBody?.parentElement;
  if (parent) parent.setAttribute("data-conflict", "stale");
  const banner = document.getElementById("detail-conflict-banner");
  if (banner) banner.removeAttribute("hidden");
}

async function _saveEdits(): Promise<void> {
  if (!_selectedNodeId || !_deps) return;
  const detail = _deps.editedDetailIndex[_selectedNodeId];
  const editedNode = getEditedNode(_selectedNodeId);
  if (!detail || !editedNode) return;
  const graph_id = _graphId();
  if (!graph_id) return;
  const changes: Record<string, unknown> = {};
  changes.label = editedNode.label;
  changes.card_sections = (detail.sections || []).map((section, order) => ({
    title: section.title || "Section",
    content: section.content || "",
    icon: section.icon || "",
    order: typeof (section as { order?: unknown }).order === "number" ? (section as { order: number }).order : order + 1,
  }));
  const response = await fetch(`/api/nodes/${encodeURIComponent(_selectedNodeId)}` , {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph_id, changes }),
  });
  if (!response.ok) return;
  _hasEdits = false;
  _clearConflictStale();
  toggleEditControls();
}

function createSectionHeading(iconName: string, label: string): HTMLHeadingElement {
  const heading = document.createElement("h3");
  heading.className = "detail-section-heading";
  const icon = document.createElement("svg");
  icon.setAttribute("class", "card-icon");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElement("use");
  use.setAttribute("href", `#icon-${iconName}`);
  icon.appendChild(use);
  const text = document.createElement("span");
  text.textContent = label;
  heading.appendChild(icon);
  heading.appendChild(text);
  return heading;
}

function appendScoreChip(container: Element, node: NodeItem): void {
  const numeric = Number((node as unknown as Record<string, unknown>).score ?? (node as unknown as Record<string, unknown>).confidence);
  if (!Number.isFinite(numeric)) return;
  const chip = document.createElement("span");
  chip.className = "detail-score-chip";
  chip.textContent = `Score ${numeric.toFixed(2)}`;
  container.appendChild(chip);
}

// ── Core rendering ─────────────────────────────────────────────────────────

function renderEvidence(evidence: EvidenceItem[]): Element {
  const root = document.createElement("section");
  root.className = "detail-section";
  root.appendChild(createSectionHeading("info", "Evidence"));
  const list = document.createElement("div");
  list.className = "evidence-list";
  evidence.forEach((item) => {
    const details = document.createElement("details");
    details.className = "evidence-item";
    const summary = document.createElement("summary");
    summary.textContent = item.content
      ? `${String(item.content).slice(0, 96)}${item.content.length > 96 ? "…" : ""}`
      : item.id;
    const typeBadge = document.createElement("span");
    typeBadge.className = "badge";
    typeBadge.textContent = item.type ?? "evidence";
    summary.prepend(typeBadge);
    details.appendChild(summary);
    const body = document.createElement("div");
    const source = document.createElement("div");
    source.className = "evidence-source";
    source.textContent = `Source: ${item.source ?? "unknown"}`;
    body.appendChild(source);
    if (item.provenance) {
      const prov = document.createElement("pre");
      prov.className = "relationship-evidence";
      prov.textContent = JSON.stringify(item.provenance, null, 2);
      body.appendChild(prov);
    }
    details.appendChild(body);
    list.appendChild(details);
  });
  root.appendChild(list);
  return root;
}

function renderRelationships(relationships: Relationships): Element | null {
  const incoming = (relationships.incoming ?? []).map((row) => ({ ...row, direction: "incoming" as const }));
  const outgoing = (relationships.outgoing ?? []).map((row) => ({ ...row, direction: "outgoing" as const }));
  const rows = incoming.concat(outgoing);
  const root = document.createElement("section");
  root.className = "detail-section";
  root.appendChild(createSectionHeading("chevron-right", "Relationship rationale"));
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No relationships";
    root.appendChild(empty);
    return root;
  }
  const grouped = new Map<string, Array<RelationshipRow & { direction: "incoming" | "outgoing" }>>();
  rows.forEach((row) => {
    const key = String(row.edge_label || "RELATED");
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(row);
  });
  Array.from(grouped.keys()).sort((a, b) => a.localeCompare(b)).forEach((relationshipType) => {
    const groupedRows = grouped.get(relationshipType) ?? [];
    const group = document.createElement("div");
    group.className = "relationship-group";
    const gHeading = document.createElement("h4");
    gHeading.textContent = relationshipType;
    group.appendChild(gHeading);
    const list = document.createElement("ul");
    list.className = "relationship-list";
    groupedRows.forEach((row) => {
      const li = document.createElement("li");
      const name = row.direction === "incoming" ? row.source_label : row.target_label;
      const summary = document.createElement("button");
      summary.type = "button";
      summary.className = "detail-ellipsis";
      summary.title = `${name ?? ""} · ${row.edge_label ?? ""}`;
      summary.textContent = `${arrow[row.direction]} ${name} · ${row.edge_label}`;
      summary.setAttribute("data-target-id", String((row.direction === "incoming" ? row.source_id : row.target_id) ?? ""));
      summary.addEventListener("click", () => {
        const targetId = summary.getAttribute("data-target-id") || "";
        if (!targetId) return;
        // click-to-focus bridge: window.brainDsUI.network
        const network = (window as unknown as { brainDsUI?: { network?: { focus?: (id: string, options?: unknown) => void } } }).brainDsUI?.network;
        if (network && typeof network.focus === "function") {
          network.focus(targetId, { animation: true });
        }
      });
      li.appendChild(summary);
      if ((row.reasons ?? []).length) {
        const reasons = document.createElement("div");
        reasons.className = "relationship-reasons";
        reasons.textContent = `Reasons: ${(row.reasons ?? []).join("; ")}`;
        li.appendChild(reasons);
      }
      if ((row.evidence_ids ?? []).length) {
        const evidenceIds = document.createElement("div");
        evidenceIds.className = "relationship-evidence";
        evidenceIds.textContent = `Evidence IDs: ${(row.evidence_ids ?? []).join(", ")}`;
        li.appendChild(evidenceIds);
      }
      list.appendChild(li);
    });
    group.appendChild(list);
    root.appendChild(group);
  });
  return root;
}

export function collapseDetailPanel(collapsed: boolean): void {
  if (!_detailPanel || !_detailCollapseBtn) return;
  _detailPanel.classList.toggle("is-collapsed", collapsed);
  _detailCollapseBtn.setAttribute("aria-expanded", String(!collapsed));
  _detailCollapseBtn.textContent = collapsed ? "Expand" : "Collapse";
}

export function renderDetailPanel(nodeId: string | null): void {
  // If in edit mode and a nodeId is given, delegate to editable renderer.
  if (_editMode && nodeId) {
    renderDetailPanelEditable(nodeId);
    return;
  }
  if (!_deps || !_detailPanel || !_detailTitle || !_detailMeta || !_detailBody || !_editToggleBtn) return;
  const detail = nodeId ? _deps.editedDetailIndex[nodeId] : null;
  if (!detail) {
    _editMode = false;
    _editToggleBtn.setAttribute("aria-pressed", "false");
    _detailPanel.classList.add("is-empty");
    _detailBody.setAttribute("data-state", "empty");
    _detailTitle.textContent = "Node details";
    _detailMeta.textContent = "Select a node to view details";
    _detailBody.textContent = "Select a node to view details";
    toggleEditControls();
    collapseDetailPanel(false);
    return;
  }
  _detailPanel.classList.remove("is-empty");
  _clearConflictStale();
  _detailBody.setAttribute("data-state", "ready");
  _detailTitle.textContent = detail.node.label ?? detail.node.id;
  _detailMeta.textContent = `${detail.node.type} · ${detail.node.supertype}`;
  _detailBody.innerHTML = "";
  appendScoreChip(_detailBody, detail.node);

  const sections = detail.sections ?? [];
  let rendered = false;
  sections.forEach((section) => {
    const article = document.createElement("article");
    article.className = section.is_gap ? "detail-card section--gap" : "detail-card";
    (article as HTMLElement).style.setProperty(
      "--card-accent",
      section.accent_color ?? detail.node.color ?? ""
    );
    if (section.icon) {
      const iconEl = document.createElement("span");
      iconEl.className = "card-icon";
      iconEl.textContent = section.icon;
      article.appendChild(iconEl);
    }
    const heading = document.createElement("h3");
    heading.textContent = section.title ?? "Section";
    const content = document.createElement("p");
    content.textContent = section.is_gap
      ? "[Information Missing / Pending Capture]"
      : (section.content ?? "");
    article.appendChild(heading);
    article.appendChild(content);
    _detailBody!.appendChild(article);
  });
  if (sections.length) rendered = true;

  const relationships = renderRelationships(detail.relationships ?? {});
  if (relationships) {
    _detailBody.appendChild(relationships);
    rendered = true;
  }
  const evidence = detail.evidence ?? [];
  if (evidence.length) {
    _detailBody.appendChild(renderEvidence(evidence));
    rendered = true;
  }
  if (!rendered) {
    _detailBody.textContent = "No details available";
  }
  toggleEditControls();
  collapseDetailPanel(false);
}

export function renderDetailPanelEditable(nodeId: string): void {
  if (!_deps || !_detailPanel || !_detailTitle || !_detailMeta || !_detailBody || !_editToggleBtn) return;
  const detail = _deps.editedDetailIndex[nodeId] ?? null;
  const editedNode = getEditedNode(nodeId);
  if (!detail || !editedNode) {
    renderDetailPanel(nodeId);
    return;
  }
  _detailPanel.classList.remove("is-empty");
  _clearConflictStale();
  _detailBody.setAttribute("data-state", "ready");
  _detailTitle.textContent = editedNode.label ?? detail.node.label ?? editedNode.id;
  _detailMeta.textContent = `${detail.node.type} · ${detail.node.supertype}`;
  _detailBody.innerHTML = "";
  appendScoreChip(_detailBody, detail.node);

  const titleWrap = document.createElement("div");
  titleWrap.className = "detail-card";
  const titleHeading = document.createElement("h3");
  titleHeading.textContent = "Label";
  titleWrap.appendChild(titleHeading);
  if (isFieldEditable(detail.node ?? editedNode, "label")) {
    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.value = editedNode.label ?? "";
    labelInput.addEventListener("input", () => {
      editedNode.label = labelInput.value;
      if (detail.node) detail.node.label = labelInput.value;
      _hasEdits = true;
      toggleEditControls();
    });
    labelInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") labelInput.blur();
    });
    titleWrap.appendChild(labelInput);
    labelInput.focus();
  } else {
    const readOnlyLabel = document.createElement("p");
    readOnlyLabel.textContent = editedNode.label ?? "";
    titleWrap.appendChild(readOnlyLabel);
  }
  _detailBody.appendChild(titleWrap);

  const sections = detail.sections ?? [];
  let rendered = true;
  sections.forEach((section, sectionIndex) => {
    const article = document.createElement("article");
    article.className = "detail-card";
    (article as HTMLElement).style.setProperty(
      "--card-accent",
      section.accent_color ?? detail.node.color ?? ""
    );
    if (section.icon) {
      const iconEl = document.createElement("span");
      iconEl.className = "card-icon";
      iconEl.textContent = section.icon;
      article.appendChild(iconEl);
    }
    const heading = document.createElement("h3");
    heading.textContent = section.title ?? "Section";
    article.appendChild(heading);
    const sectionField = normalizeFieldName(section.title ?? "details");
    if (
      isFieldEditable(detail.node ?? editedNode, sectionField) ||
      isFieldEditable(detail.node ?? editedNode, "details")
    ) {
      const textarea = document.createElement("textarea");
      textarea.value = section.content ?? "";
      textarea.rows = Math.max(3, Math.min(10, Math.ceil((textarea.value.length || 1) / 48)));
      textarea.addEventListener("input", () => {
        section.content = textarea.value;
        if (detail.sections?.[sectionIndex]) {
          detail.sections[sectionIndex].content = textarea.value;
        }
        _hasEdits = true;
        toggleEditControls();
      });
      article.appendChild(textarea);
    } else {
      const readOnlyContent = document.createElement("p");
      readOnlyContent.textContent = section.content ?? "";
      article.appendChild(readOnlyContent);
    }
    _detailBody!.appendChild(article);
  });

  const relationships = renderRelationships(detail.relationships ?? {});
  if (relationships) {
    _detailBody.appendChild(relationships);
  }
  const evidence = detail.evidence ?? [];
  if (evidence.length) {
    _detailBody.appendChild(renderEvidence(evidence));
  }
  if (!sections.length && !evidence.length && !relationships) {
    rendered = false;
  }
  if (!rendered) {
    _detailBody.textContent = "No details available";
  }
  const firstEditable = _detailBody.querySelector("input:not([disabled]), textarea:not([disabled])") as
    | HTMLInputElement
    | HTMLTextAreaElement
    | null;
  if (firstEditable) firstEditable.focus();
  toggleEditControls();
  collapseDetailPanel(false);
}

// ── Lifecycle ──────────────────────────────────────────────────────────────

/**
 * mount(root, deps) — design §1.2 lifecycle entry point.
 *
 * @param root   The aside#detail-panel element.
 * @param deps   External dependencies injected by the template.
 */
export function mount(root: Element, deps: DetailPanelDeps): void {
  _root = root;
  _deps = deps;
  _listeners = [];
  _editMode = false;
  _selectedNodeId = null;
  _hasEdits = false;

  // Cache DOM refs from root (avoids global document queries inside module)
  _detailPanel = root;
  _detailTitle = root.closest("body")
    ? document.getElementById("detail-title")
    : root.querySelector("#detail-title");
  _detailMeta = document.getElementById("detail-meta");
  _detailBody = document.getElementById("detail-body");
  _editToggleBtn = document.getElementById("edit-toggle") as HTMLButtonElement | null;
  _exportJsonBtn = document.getElementById("export-json") as HTMLButtonElement | null;
  _detailSaveBtn = document.getElementById("detail-save") as HTMLButtonElement | null;
  _detailCollapseBtn = document.getElementById("detail-collapse") as HTMLButtonElement | null;

  if (_detailSaveBtn) {
    _on(_detailSaveBtn, "click", () => {
      void _saveEdits();
    });
  }

  // Wire edit toggle
  if (_editToggleBtn) {
    _on(_editToggleBtn, "click", () => {
      _editMode = !(_editMode && _selectedNodeId !== null);
      _editToggleBtn!.setAttribute("aria-pressed", String(_editMode));
      if (!_selectedNodeId) {
        renderDetailPanel(null);
        return;
      }
      if (_editMode) {
        renderDetailPanelEditable(_selectedNodeId);
      } else {
        renderDetailPanel(_selectedNodeId);
      }
    });
  }

  // Wire collapse button
  if (_detailCollapseBtn) {
    _on(_detailCollapseBtn, "click", () => {
      collapseDetailPanel(!_detailPanel!.classList.contains("is-collapsed"));
    });
  }

  // Wire detail panel keydown (Esc to exit edit or clear)
  if (_detailPanel) {
    _on(_detailPanel, "keydown", (event: Event) => {
      const kev = event as KeyboardEvent;
      if (kev.key === "Escape") {
        kev.preventDefault();
        if (_editMode) {
          _editMode = false;
          if (_editToggleBtn) _editToggleBtn.setAttribute("aria-pressed", "false");
          _clearConflictStale();
          if (_selectedNodeId) renderDetailPanel(_selectedNodeId);
          return;
        }
        renderDetailPanel(null);
      }
    });
  }

  // Subscribe to select-change for multi-select tiered panel
  if (deps.network && typeof deps.network.on === "function") {
    deps.network.on("select-change", (params: unknown) => {
      const p = params as { nodes?: string[] };
      const selectedIds = p?.nodes ?? [];
      setSelectedNodeId(selectedIds.length === 1 ? selectedIds[0] : null);
      renderDetailPanel(_selectedNodeId);
    });
  }
}

/**
 * unmount() — teardown. Removes all registered event listeners.
 */
export function unmount(): void {
  _listeners.forEach(({ el, type, fn }) => {
    el.removeEventListener(type, fn);
  });
  _listeners = [];
  _root = null;
  _deps = null;
  _detailPanel = null;
  _detailTitle = null;
  _detailMeta = null;
  _detailBody = null;
  _editToggleBtn = null;
  _exportJsonBtn = null;
  _detailCollapseBtn = null;
  _editMode = false;
  _selectedNodeId = null;
  _hasEdits = false;
  _detailSaveBtn = null;
}

// ── Public API beyond mount/unmount ────────────────────────────────────────

/** Called by template when user clicks a node or focusNode() runs. */
export function setSelectedNodeId(nodeId: string | null): void {
  _selectedNodeId = nodeId;
}

/** Called by template to get current selectedNodeId (for edit-mode re-render). */
export function getSelectedNodeId(): string | null {
  return _selectedNodeId;
}

/** Called by template to set edit mode programmatically. */
export function setEditMode(enabled: boolean): void {
  _editMode = Boolean(enabled && _selectedNodeId !== null);
  if (!_editMode) _clearConflictStale();
  if (_editToggleBtn) _editToggleBtn.setAttribute("aria-pressed", String(_editMode));
  if (_selectedNodeId === null) {
    renderDetailPanel(null);
    return;
  }
  if (_editMode) {
    renderDetailPanelEditable(_selectedNodeId);
  } else {
    renderDetailPanel(_selectedNodeId);
  }
}

/** Called by template to get current hasEdits state. */
export function getHasEdits(): boolean {
  return _hasEdits;
}

export function isEditMode(): boolean {
  return _editMode;
}

export function markConflictStale(): void {
  _markConflictStale();
}

export function clearConflictStale(): void {
  _clearConflictStale();
}
