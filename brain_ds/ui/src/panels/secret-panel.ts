// panels/secret-panel.ts — Workspace secret settings panel.
//
// Right-rail panel that lists workspace secret handles, lets the operator add
// new handles, and remove existing ones. Raw values are NEVER rendered; the
// server returns redacted metadata only.

// ── Types ──────────────────────────────────────────────────────────────────

export interface SecretPanelDeps {
  graphId: string;
  apiBase?: string;
}

interface SecretHandle {
  handle: string;
  kind: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

interface SecretSchema {
  schema_version: string;
  provider_kinds: Record<string, { required: string[]; types: Record<string, string> }>;
}

// ── Module state ───────────────────────────────────────────────────────────

let _deps: SecretPanelDeps | null = null;
let _panelEl: HTMLElement | null = null;
let _listeners: Array<{ target: EventTarget; type: string; handler: EventListenerOrEventListenerObject }> = [];
let _handles: SecretHandle[] = [];
let _schema: SecretSchema | null = null;
let _abort: AbortController | null = null;

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
  const url = `${_apiUrl('/secrets/schema')}?graph_id=${encodeURIComponent(_deps.graphId)}`;
  try {
    const res = await fetch(url, { signal: _abort?.signal ?? null });
    if (!res.ok) return null;
    return (await res.json()) as SecretSchema;
  } catch (_e) {
    return null;
  }
}

async function _loadHandles(): Promise<SecretHandle[]> {
  if (!_deps) return [];
  const url = `${_apiUrl('/secrets')}?graph_id=${encodeURIComponent(_deps.graphId)}`;
  try {
    const res = await fetch(url, { signal: _abort?.signal ?? null });
    if (!res.ok) return [];
    const data = (await res.json()) as { handles?: SecretHandle[] };
    return data.handles ?? [];
  } catch (_e) {
    return [];
  }
}

async function _addSecret(payload: Record<string, unknown>): Promise<boolean> {
  if (!_deps) return false;
  const url = `${_apiUrl('/secrets')}?graph_id=${encodeURIComponent(_deps.graphId)}`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: _abort?.signal ?? null,
    });
    return res.ok;
  } catch (_e) {
    return false;
  }
}

async function _removeSecret(handle: string): Promise<boolean> {
  if (!_deps) return false;
  const url = `${_apiUrl('/secrets')}/${encodeURIComponent(handle)}?graph_id=${encodeURIComponent(_deps.graphId)}`;
  try {
    const res = await fetch(url, { method: 'DELETE', signal: _abort?.signal ?? null });
    return res.ok;
  } catch (_e) {
    return false;
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
  empty.innerHTML = `<p>No hay secretos configurados en este workspace.</p>`;
  return empty;
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
    <div class="secret-field-row">
      <label for="secret-new-value">Valor de credencial</label>
      <input id="secret-new-value" class="secret-input" type="password" autocomplete="off" placeholder="••••" required />
    </div>
    <button type="submit" class="pill-btn btn-outline secret-add-btn">
      Agregar secreto
    </button>
  `;
  return form;
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
  const fields = Object.entries(contract.types)
    .map(([name, type]) => {
      const isRequired = required.has(name);
      const inputType = type === 'integer' || type === 'number' ? 'number' : 'text';
      return `
        <div class="secret-field-row">
          <label for="secret-field-${name}">${_escapeHtml(name)}${isRequired ? ' *' : ''}</label>
          <input id="secret-field-${name}" class="secret-input secret-kind-field" data-field-name="${_escapeHtml(name)}" type="${inputType}" ${isRequired ? 'required' : ''} />
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
  _handles = await _loadHandles();
  if (_panelEl) _renderPanel();
}

function _renderPanel(): void {
  if (!_panelEl) return;
  _panelEl.innerHTML = '';

  _panelEl.appendChild(_renderHeader());

  if (_handles.length === 0) {
    _panelEl.appendChild(_renderEmpty());
  } else {
    _panelEl.appendChild(_renderList());
  }

  const form = _renderAddForm();
  _panelEl.appendChild(form);

  const kindSelect = form.querySelector('#secret-new-kind') as HTMLSelectElement | null;
  const fieldsContainer = form.querySelector('#secret-kind-fields') as HTMLElement | null;
  if (kindSelect && fieldsContainer) {
    _on(kindSelect, 'change', () => _updateKindFields(fieldsContainer, kindSelect.value));
  }

  _on(form, 'submit', async (event) => {
    event.preventDefault();
    const handleInput = form.querySelector('#secret-new-handle') as HTMLInputElement | null;
    const kindInput = form.querySelector('#secret-new-kind') as HTMLSelectElement | null;
    const valueInput = form.querySelector('#secret-new-value') as HTMLInputElement | null;
    if (!handleInput || !kindInput || !valueInput) return;

    const payload = {
      handle: handleInput.value.trim(),
      kind: kindInput.value,
      metadata: _collectMetadata(form),
      raw_value: valueInput.value,
    };

    const ok = await _addSecret(payload);
    const status = _renderStatus(ok ? 'Secreto agregado' : 'No se pudo agregar el secreto', !ok);
    form.appendChild(status);
    if (ok) {
      handleInput.value = '';
      kindInput.value = '';
      valueInput.value = '';
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
      await _refreshPanel();
    });
  });
}

// ── Public lifecycle ───────────────────────────────────────────────────────

export async function mount(panelEl: HTMLElement, deps: SecretPanelDeps): Promise<{ refresh: () => Promise<void>; unmount: () => void }> {
  if (!panelEl) return { refresh: async () => {}, unmount: () => {} };

  _panelEl = panelEl;
  _deps = deps;
  _handles = [];
  _schema = null;
  _listeners = [];
  _abort = new AbortController();

  _schema = await _loadSchema();
  _handles = await _loadHandles();
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
    },
  };
}
