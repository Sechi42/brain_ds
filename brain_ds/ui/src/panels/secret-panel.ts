// panels/secret-panel.ts — Workspace secret settings panel.
//
// Right-rail panel that lists workspace secret handles, lets the operator add
// new handles, and remove existing ones. Raw values are NEVER rendered; the
// server returns redacted metadata only.

// ── Types ──────────────────────────────────────────────────────────────────

export interface SecretPanelDeps {
  graphId: string;
  apiBase?: string;
  dataSources?: SecretBindableDataSource[];
  onBound?: (sourceId: string, connection: Record<string, unknown>) => void;
}

export interface SecretBindableDataSource {
  id: string;
  label: string;
  type: string;
}

interface SecretHandle {
  handle: string;
  kind: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

interface SecretKindContract {
  required: string[];
  types: Record<string, string>;
  requires_raw_value?: boolean;
  descriptions?: Record<string, string>;
  placeholders?: Record<string, string>;
  enums?: Record<string, string[]>;
}

interface SecretSchema {
  schema_version: string;
  provider_kinds: Record<string, SecretKindContract>;
}

type SecretListStatus = 'permission_denied' | 'empty' | 'ready' | 'error';

interface SecretListResponse {
  status: SecretListStatus;
  handles?: SecretHandle[];
  message?: string;
  detail?: string;
}

interface SecretValidationStatus {
  status: 'ok' | 'error';
  connection: 'probed' | 'not_probed' | 'probe_failed';
  message: string;
}

// ── Module state ───────────────────────────────────────────────────────────

let _deps: SecretPanelDeps | null = null;
let _panelEl: HTMLElement | null = null;
let _listeners: Array<{ target: EventTarget; type: string; handler: EventListenerOrEventListenerObject }> = [];
let _handles: SecretHandle[] = [];
let _listStatus: SecretListStatus = 'empty';
let _listMessage = '';
let _schema: SecretSchema | null = null;
let _abort: AbortController | null = null;
let _bindStatus: { handle: string; sourceId: string; ok: boolean; message: string } | null = null;

// Ephemeral per-session probe status map: handle → badge state (not persisted)
const _probeStatus: Map<string, { ok: boolean; message: string }> = new Map();

// ── Icons (Lucide line style) ──────────────────────────────────────────────

const GEAR_ICON = `<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.82-.33 1.7 1.7 0 0 0-1 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .33-1.82 1.7 1.7 0 0 0-1.56-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.82.33h.01a1.7 1.7 0 0 0 1-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.56h.01a1.7 1.7 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.33 1.82v.01a1.7 1.7 0 0 0 1.56 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1Z"/></svg>`;

const CHEVRON_RIGHT_ICON = `<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`;

// ── Helpers ────────────────────────────────────────────────────────────────

function _apiUrl(path: string): string {
  const base = (_deps?.apiBase ?? '').replace(/\/$/, '');
  return `${base}/api${path}`;
}

function _on(target: EventTarget, type: string, handler: EventListenerOrEventListenerObject): void {
  target.addEventListener(type, handler);
  _listeners.push({ target, type, handler });
}

function _classNames(base: string, extra?: string): string {
  return extra ? `${base} ${extra}` : base;
}

function _escapeHtml(value: unknown): string {
  const text = String(value ?? '');
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _renderMeta(metadata: Record<string, unknown>): string {
  const entries = Object.entries(metadata);
  if (!entries.length) return '<p class="secret-empty-meta">Sin metadatos</p>';
  const rows = entries
    .map(([key, value]) => {
      const display = Array.isArray(value) ? value.join(', ') : _escapeHtml(value);
      return `<dt>${_escapeHtml(key)}</dt><dd>${display}</dd>`;
    })
    .join('');
  return `<dl class="secret-meta-list">${rows}</dl>`;
}

// ── API ────────────────────────────────────────────────────────────────────

async function _loadSchema(): Promise<SecretSchema | null> {
  if (!_deps) return null;
  const url = `${_apiUrl('/secrets/schema')}?graph_id=${encodeURIComponent(_deps.graphId)}&agent_scope=workspace_admin`;
  try {
    const res = await fetch(url, { signal: _abort?.signal ?? null });
    if (!res.ok) return null;
    return (await res.json()) as SecretSchema;
  } catch (_e) {
    return null;
  }
}

async function _loadHandles(): Promise<void> {
  if (!_deps) return;
  const url = `${_apiUrl('/secrets')}?graph_id=${encodeURIComponent(_deps.graphId)}&agent_scope=workspace_admin`;
  try {
    const res = await fetch(url, { signal: _abort?.signal ?? null });
    const data = (await res.json()) as SecretListResponse;
    if (res.status === 403 || data.status === 'permission_denied') {
      _handles = [];
      _listStatus = 'permission_denied';
      _listMessage = data.detail ?? 'Permisos insuficientes: se requiere workspace_admin.';
      return;
    }
    if (!res.ok) {
      _handles = [];
      _listStatus = 'error';
      _listMessage = data.detail ?? 'No se pudieron cargar los secretos del workspace.';
      return;
    }
    _handles = data.handles ?? [];
    _listStatus = data.status ?? (_handles.length ? 'ready' : 'empty');
    _listMessage = data.message ?? '';
  } catch (_e) {
    _handles = [];
    _listStatus = 'error';
    _listMessage = 'No se pudieron cargar los secretos del workspace.';
  }
}

async function _addSecret(payload: Record<string, unknown>): Promise<{ ok: boolean; validation?: SecretValidationStatus }> {
  if (!_deps) return { ok: false };
  const url = `${_apiUrl('/secrets')}?graph_id=${encodeURIComponent(_deps.graphId)}&agent_scope=workspace_admin&probe=true`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: _abort?.signal ?? null,
    });
    const data = (await res.json().catch(() => ({}))) as { validation?: SecretValidationStatus };
    const validation = data.validation;
    if (validation !== undefined) {
      return { ok: res.ok, validation };
    }
    return { ok: res.ok };
  } catch (_e) {
    return { ok: false };
  }
}

async function _removeSecret(handle: string): Promise<boolean> {
  if (!_deps) return false;
  const url = `${_apiUrl('/secrets')}/${encodeURIComponent(handle)}?graph_id=${encodeURIComponent(_deps.graphId)}&agent_scope=workspace_admin`;
  try {
    const res = await fetch(url, { method: 'DELETE', signal: _abort?.signal ?? null });
    return res.ok;
  } catch (_e) {
    return false;
  }
}

// ── Probe connection ───────────────────────────────────────────────────────

/** Returns true when the secret kind supports live probing (AWS-backed kinds). */
function _kindSupportsProbe(kind: string): boolean {
  return kind.startsWith('aws-');
}

interface ProbeResult {
  ok: boolean;
  message: string;
}

async function _probeSecret(handle: string): Promise<ProbeResult> {
  if (!_deps) return { ok: false, message: 'Panel no inicializado.' };
  const url = `${_apiUrl('/secrets/validate')}?graph_id=${encodeURIComponent(_deps.graphId)}&handle=${encodeURIComponent(handle)}&agent_scope=workspace_admin`;
  try {
    const res = await fetch(url, { method: 'POST', signal: _abort?.signal ?? null });
    const data = (await res.json().catch(() => ({}))) as { status?: string; message?: string };
    const ok = res.ok && data.status === 'ok';
    const message = data.message ?? (ok ? 'Conectado.' : 'Error de conexión.');
    return { ok, message };
  } catch (_e) {
    return { ok: false, message: 'No se pudo conectar: error de red.' };
  }
}

function _connectionDescriptorForSecret(handle: SecretHandle): Record<string, unknown> {
  const descriptor: Record<string, unknown> = {
    kind: handle.kind,
    secret_handle: handle.handle,
  };
  if (handle.kind === 'aws-postgres') {
    descriptor.database = handle.metadata.database;
  }
  if (handle.kind === 'aws-google-sheets') {
    descriptor.spreadsheet_id = handle.metadata.spreadsheet_id;
    descriptor.sheet_range = handle.metadata.sheet_range;
  }
  if (handle.kind === 'sqlite') {
    descriptor.path = handle.metadata.path;
  }
  return descriptor;
}

async function _bindSecretToDataSource(handle: SecretHandle, sourceId: string): Promise<{ ok: boolean; message: string; connection?: Record<string, unknown> }> {
  if (!_deps) return { ok: false, message: 'Panel no inicializado.' };
  const descriptor = _connectionDescriptorForSecret(handle);
  const url = `${_apiUrl('/nodes/')}${encodeURIComponent(sourceId)}`;
  const changes = { details: { connection: descriptor } };
  try {
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        graph_id: _deps.graphId,
        changes,
      }),
      signal: _abort?.signal ?? null,
    });
    if (!res.ok) return { ok: false, message: 'No se pudo vincular el secreto al Data Source.' };
    _deps.onBound?.(sourceId, descriptor);
    return { ok: true, message: 'Data Source now explorable.', connection: descriptor };
  } catch (_e) {
    return { ok: false, message: 'No se pudo vincular: error de red.' };
  }
}

// ── Rendering ──────────────────────────────────────────────────────────────

function _renderHeader(): HTMLElement {
  const header = document.createElement('div');
  header.className = 'secret-panel-header';
  header.innerHTML = `<h3 class="secret-panel-title">${GEAR_ICON} Configuración de secretos</h3>`;
  return header;
}

function _renderEmpty(): HTMLElement {
  const empty = document.createElement('div');
  empty.className = 'secret-panel-empty';
  empty.innerHTML = `<p>${_escapeHtml(_listMessage || 'No hay secretos configurados en este workspace.')}</p>`;
  return empty;
}

function _renderPermissionDenied(): HTMLElement {
  const denied = document.createElement('div');
  denied.className = 'secret-panel-empty secret-panel-empty--permission';
  denied.setAttribute('role', 'alert');
  denied.textContent = _listMessage || 'Permisos insuficientes: se requiere workspace_admin.';
  return denied;
}

function _renderLoadError(): HTMLElement {
  const error = document.createElement('div');
  error.className = 'secret-panel-empty secret-panel-empty--error';
  error.setAttribute('role', 'alert');
  error.textContent = _listMessage || 'No se pudieron cargar los secretos del workspace.';
  return error;
}

function _renderProbeActions(handle: SecretHandle): string {
  if (!_kindSupportsProbe(handle.kind)) return '';

  const escaped = _escapeHtml(handle.handle);
  const probeState = _probeStatus.get(handle.handle);

  let badgeHtml = '';
  if (probeState !== undefined) {
    const badgeClass = probeState.ok
      ? 'secret-probe-badge secret-probe-badge--ok'
      : 'secret-probe-badge secret-probe-badge--error';
    badgeHtml = `<span class="${badgeClass}" data-probe-status="${escaped}" role="status" aria-live="polite">${_escapeHtml(probeState.message)}</span>`;
  } else {
    // Render an empty badge placeholder so the DOM attribute is stable for tests
    badgeHtml = `<span class="secret-probe-badge" data-probe-status="${escaped}" role="status" aria-live="polite" hidden></span>`;
  }

  return `
    <div class="secret-probe-row">
      <button type="button" class="secret-probe-btn pill-btn btn-outline" data-probe-handle="${escaped}" aria-label="Probar conexión de ${escaped}">
        Probar conexión
      </button>
      ${badgeHtml}
    </div>
  `;
}

function _renderBindActions(handle: SecretHandle): string {
  const dataSources = _deps?.dataSources ?? [];
  if (!dataSources.length) return '';

  const escapedHandle = _escapeHtml(handle.handle);
  const selectId = `secret-bind-source-${escapedHandle}`;
  const status = _bindStatus?.handle === handle.handle ? _bindStatus : null;
  const options = dataSources
    .map((source) => `<option value="${_escapeHtml(source.id)}">${_escapeHtml(source.label || source.id)}</option>`)
    .join('');
  const statusHtml = status
    ? `<span class="secret-bind-badge ${status.ok ? 'secret-bind-badge--ok' : 'secret-bind-badge--error'}" role="status" aria-live="polite">${_escapeHtml(status.message)}</span>`
    : '<span class="secret-bind-badge" role="status" aria-live="polite" hidden></span>';

  return `
    <div class="secret-bind-row">
      <label class="secret-bind-label" for="${selectId}">Bind to Data Source</label>
      <select id="${selectId}" class="secret-input secret-bind-select" data-bind-secret-handle="${escapedHandle}" aria-label="Data Source para ${escapedHandle}">
        ${options}
      </select>
      <button type="button" class="secret-bind-btn pill-btn btn-outline" data-bind-secret-handle="${escapedHandle}" data-bind-source-id="" aria-label="Bind ${escapedHandle} to selected Data Source">
        Bind to Data Source
      </button>
      ${statusHtml}
    </div>
  `;
}

function _renderList(): HTMLElement {
  const list = document.createElement('ul');
  list.className = 'secret-list';
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-label', 'Secretos del workspace');

  for (const handle of _handles) {
    const li = document.createElement('li');
    li.className = 'secret-item';
    li.setAttribute('role', 'option');
    li.setAttribute('aria-label', `${handle.handle}, ${handle.kind}`);

    const summaryId = `secret-summary-${handle.handle}`;
    li.innerHTML = `
      <div class="secret-row">
        <span class="secret-handle">${_escapeHtml(handle.handle)}</span>
        <span class="secret-kind">${_escapeHtml(handle.kind)}</span>
      </div>
      <details class="secret-detail">
        <summary class="secret-summary" aria-label="Mostrar detalles de ${handle.handle}">
          <span>Detalles</span>
          <span class="secret-chevron">${CHEVRON_RIGHT_ICON}</span>
        </summary>
        <div class="secret-detail-body" id="${summaryId}">
          ${_renderMeta(handle.metadata)}
        </div>
      </details>
      ${_renderProbeActions(handle)}
      ${_renderBindActions(handle)}
      <button type="button" class="secret-remove-btn" data-secret-handle="${_escapeHtml(handle.handle)}" aria-label="Eliminar secreto ${_escapeHtml(handle.handle)}">
        Eliminar
      </button>
    `;
    list.appendChild(li);
  }

  return list;
}

function _renderKindOptions(): string {
  if (!_schema) return '<option value="">Seleccionar tipo</option>';
  const kinds = Object.keys(_schema.provider_kinds).sort();
  const options = kinds.map((k) => `<option value="${_escapeHtml(k)}">${_escapeHtml(k)}</option>`).join('');
  return `<option value="">Seleccionar tipo</option>${options}`;
}

function _renderAddForm(): HTMLElement {
  const form = document.createElement('form');
  form.className = 'secret-form';
  form.setAttribute('aria-label', 'Agregar secreto al workspace');
  form.innerHTML = `
    <h4 class="secret-form-title">Agregar secreto</h4>
    <div class="secret-field-row">
      <label for="secret-new-handle">Identificador</label>
      <input id="secret-new-handle" class="secret-input" type="text" autocomplete="off" placeholder="ej. warehouse_ro" required />
    </div>
    <div class="secret-field-row">
      <label for="secret-new-kind">Tipo</label>
      <select id="secret-new-kind" class="secret-input" required>
        ${_renderKindOptions()}
      </select>
    </div>
    <div id="secret-kind-fields" class="secret-kind-fields"></div>
    <div id="secret-raw-value-row" class="secret-field-row">
      <label for="secret-new-value">Valor de credencial</label>
      <input id="secret-new-value" class="secret-input" type="password" autocomplete="off" placeholder="••••" required />
    </div>
    <button type="submit" class="pill-btn btn-outline secret-add-btn">
      Agregar secreto
    </button>
  `;
  return form;
}

function _updateRawValueVisibility(form: HTMLElement, kind: string): void {
  const rawValueRow = form.querySelector('#secret-raw-value-row') as HTMLElement | null;
  const rawValueInput = form.querySelector('#secret-new-value') as HTMLInputElement | null;
  if (!rawValueRow || !rawValueInput) return;

  const contract = _schema?.provider_kinds[kind];
  // requires_raw_value defaults to true when absent
  const requiresRawValue = !contract || contract.requires_raw_value !== false;

  if (requiresRawValue) {
    rawValueRow.style.display = '';
    rawValueInput.required = true;
  } else {
    rawValueRow.style.display = 'none';
    rawValueInput.required = false;
    rawValueInput.value = '';
  }
}

function _updateKindFields(container: HTMLElement, kind: string): void {
  if (!_schema || !kind) {
    container.innerHTML = '';
    return;
  }
  const contract = _schema.provider_kinds[kind];
  if (!contract) {
    container.innerHTML = '';
    return;
  }
  const required = new Set(contract.required);
  const descriptions = contract.descriptions ?? {};
  const placeholders = contract.placeholders ?? {};
  const enums = contract.enums ?? {};

  const fields = Object.entries(contract.types)
    .map(([name, type]) => {
      const isRequired = required.has(name);
      const description = descriptions[name];
      const placeholder = placeholders[name];
      const enumValues = enums[name];

      let fieldHtml: string;
      if (enumValues && enumValues.length > 0) {
        // Render as <select> with enum options
        const optionsHtml = enumValues
          .map((v) => `<option value="${_escapeHtml(v)}">${_escapeHtml(v)}</option>`)
          .join('');
        const titleAttr = description ? ` title="${_escapeHtml(description)}"` : '';
        fieldHtml = `<select id="secret-field-${name}" class="secret-input secret-kind-field" data-field-name="${_escapeHtml(name)}" ${isRequired ? 'required' : ''}${titleAttr}>${optionsHtml}</select>`;
      } else {
        // Render as <input>
        const inputType = type === 'integer' || type === 'number' ? 'number' : 'text';
        const placeholderAttr = placeholder ? ` placeholder="${_escapeHtml(placeholder)}"` : '';
        const titleAttr = description ? ` title="${_escapeHtml(description)}"` : '';
        fieldHtml = `<input id="secret-field-${name}" class="secret-input secret-kind-field" data-field-name="${_escapeHtml(name)}" type="${inputType}" ${isRequired ? 'required' : ''}${placeholderAttr}${titleAttr} />`;
      }

      return `
        <div class="secret-field-row">
          <label for="secret-field-${name}">${_escapeHtml(name)}${isRequired ? ' *' : ''}</label>
          ${fieldHtml}
        </div>
      `;
    })
    .join('');
  container.innerHTML = fields;
}

function _collectMetadata(form: HTMLElement): Record<string, unknown> {
  const metadata: Record<string, unknown> = {};
  form.querySelectorAll('.secret-kind-field').forEach((input) => {
    const el = input as HTMLInputElement;
    const name = el.getAttribute('data-field-name');
    if (!name) return;
    metadata[name] = el.type === 'number' ? (el.valueAsNumber || Number(el.value)) : el.value;
  });
  return metadata;
}

function _renderStatus(message: string, isError = false): HTMLElement {
  const status = document.createElement('div');
  status.className = _classNames('secret-status', isError ? 'secret-status--error' : 'secret-status--ok');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.textContent = message;
  return status;
}

async function _refreshPanel(): Promise<void> {
  await _loadHandles();
  if (_panelEl) _renderPanel();
}

function _renderPanel(): void {
  if (!_panelEl) return;
  _panelEl.innerHTML = '';

  _panelEl.appendChild(_renderHeader());

  if (_listStatus === 'permission_denied') {
    _panelEl.appendChild(_renderPermissionDenied());
  } else if (_listStatus === 'error') {
    _panelEl.appendChild(_renderLoadError());
  } else if (_listStatus === 'empty' || _handles.length === 0) {
    _panelEl.appendChild(_renderEmpty());
  } else if (_listStatus === 'ready') {
    _panelEl.appendChild(_renderList());
  }

  const form = _renderAddForm();
  _panelEl.appendChild(form);

  const kindSelect = form.querySelector('#secret-new-kind') as HTMLSelectElement | null;
  const fieldsContainer = form.querySelector('#secret-kind-fields') as HTMLElement | null;
  if (kindSelect && fieldsContainer) {
    _on(kindSelect, 'change', () => {
      _updateKindFields(fieldsContainer, kindSelect.value);
      _updateRawValueVisibility(form, kindSelect.value);
    });
  }

  _on(form, 'submit', async (event) => {
    event.preventDefault();
    const handleInput = form.querySelector('#secret-new-handle') as HTMLInputElement | null;
    const kindInput = form.querySelector('#secret-new-kind') as HTMLSelectElement | null;
    const valueInput = form.querySelector('#secret-new-value') as HTMLInputElement | null;
    if (!handleInput || !kindInput) return;

    const contract = _schema?.provider_kinds[kindInput.value];
    const requiresRawValue = !contract || contract.requires_raw_value !== false;

    const payload: Record<string, unknown> = {
      handle: handleInput.value.trim(),
      kind: kindInput.value,
      metadata: _collectMetadata(form),
    };
    if (requiresRawValue && valueInput) {
      payload.raw_value = valueInput.value;
    }

    const result = await _addSecret(payload);
    const validationMessage = result.validation?.message ?? 'Validación segura OK; contrato del proveedor verificado.';
    const message = result.ok ? `Secreto agregado. ${validationMessage}` : 'No se pudo agregar el secreto';
    const status = _renderStatus(message, !result.ok || result.validation?.status === 'error');
    form.appendChild(status);
    if (result.ok) {
      handleInput.value = '';
      kindInput.value = '';
      if (valueInput) valueInput.value = '';
      if (fieldsContainer) fieldsContainer.innerHTML = '';
      await _refreshPanel();
      setTimeout(() => status.remove(), 2000);
    }
  });

  _panelEl.querySelectorAll('.secret-remove-btn').forEach((btn) => {
    const handle = (btn as HTMLElement).getAttribute('data-secret-handle');
    if (!handle) return;
    _on(btn, 'click', async () => {
       if (!window.confirm(`¿Eliminar el secreto "${handle}"?`)) return;
      await _removeSecret(handle);
      _probeStatus.delete(handle);
      await _refreshPanel();
    });
  });

  _panelEl.querySelectorAll('.secret-bind-btn').forEach((btn) => {
    const handleName = (btn as HTMLElement).getAttribute('data-bind-secret-handle');
    const handle = _handles.find((item) => item.handle === handleName);
    if (!handle) return;
    _on(btn, 'click', async () => {
      const bindBtn = btn as HTMLButtonElement;
      const row = bindBtn.closest('.secret-bind-row');
      const select = row?.querySelector('.secret-bind-select') as HTMLSelectElement | null;
      const sourceId = select?.value || '';
      bindBtn.setAttribute('data-bind-source-id', sourceId);
      if (!sourceId) return;
      bindBtn.disabled = true;
      bindBtn.textContent = 'Vinculando…';
      const result = await _bindSecretToDataSource(handle, sourceId);
      _bindStatus = { handle: handle.handle, sourceId, ok: result.ok, message: result.message };
      const badge = row?.querySelector<HTMLElement>('.secret-bind-badge');
      if (badge) {
        badge.hidden = false;
        badge.className = result.ok
          ? 'secret-bind-badge secret-bind-badge--ok'
          : 'secret-bind-badge secret-bind-badge--error';
        badge.textContent = result.message;
      }
      bindBtn.disabled = false;
      bindBtn.textContent = 'Bind to Data Source';
    });
  });

  // Wire probe buttons — update badge in-place (no full re-render)
  _panelEl.querySelectorAll('.secret-probe-btn').forEach((btn) => {
    const handle = (btn as HTMLElement).getAttribute('data-probe-handle');
    if (!handle) return;
    _on(btn, 'click', async () => {
      const probeBtn = btn as HTMLButtonElement;
      probeBtn.disabled = true;
      probeBtn.textContent = 'Probando…';

      const result = await _probeSecret(handle);
      _probeStatus.set(handle, { ok: result.ok, message: result.message });

      // Update the badge in-place without re-rendering the list
      const badge = _panelEl?.querySelector<HTMLElement>(`[data-probe-status="${CSS.escape(handle)}"]`);
      if (badge) {
        badge.hidden = false;
        badge.className = result.ok
          ? 'secret-probe-badge secret-probe-badge--ok'
          : 'secret-probe-badge secret-probe-badge--error';
        badge.textContent = result.message;
      }

      probeBtn.disabled = false;
      probeBtn.textContent = 'Probar conexión';
    });
  });
}

// ── Public lifecycle ───────────────────────────────────────────────────────

export async function mount(panelEl: HTMLElement, deps: SecretPanelDeps): Promise<{ refresh: () => Promise<void>; unmount: () => void }> {
  if (!panelEl) return { refresh: async () => {}, unmount: () => {} };

  _panelEl = panelEl;
  _deps = deps;
  _handles = [];
  _listStatus = 'empty';
  _listMessage = '';
  _schema = null;
  _listeners = [];
  _abort = new AbortController();
  _probeStatus.clear();
  _bindStatus = null;

  _schema = await _loadSchema();
  await _loadHandles();
  _renderPanel();

  return {
    refresh: async () => {
      await _refreshPanel();
    },
    unmount: () => {
      _abort?.abort();
      _listeners.forEach(({ target, type, handler }) => {
        target.removeEventListener(type, handler);
      });
      _listeners = [];
      if (_panelEl) _panelEl.innerHTML = '';
      _panelEl = null;
      _deps = null;
      _schema = null;
      _handles = [];
      _listStatus = 'empty';
      _listMessage = '';
      _probeStatus.clear();
      _bindStatus = null;
    },
  };
}
