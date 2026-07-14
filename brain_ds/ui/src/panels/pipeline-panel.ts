// @ts-nocheck
// panels/pipeline-panel.ts — read-only pipeline stage rail panel.

export const PIPELINE_STAGES = [
  { key: 'setup', label: 'Setup' },
  { key: 'intake', label: 'Intake' },
  { key: 'map', label: 'Map' },
  { key: 'brd', label: 'BRD' },
  { key: 'verify', label: 'Verify' },
  { key: 'archive', label: 'Archive' },
] as const;

type PipelineStageKey = typeof PIPELINE_STAGES[number]['key'];
type PipelineStageStatus = 'pending' | 'running' | 'done' | 'blocked' | 'error';

export interface PipelinePanelDeps {
  graphId: string;
  stageStatuses?: Partial<Record<PipelineStageKey, PipelineStageStatus>>;
}

type PipelineStageView = typeof PIPELINE_STAGES[number] & { status: PipelineStageStatus };

let _deps: PipelinePanelDeps | null = null;
let _panelEl: HTMLElement | null = null;
let _listeners: Array<{ target: EventTarget; type: string; handler: EventListenerOrEventListenerObject }> = [];

const STATUS_LABELS: Record<PipelineStageStatus, string> = {
  pending: 'Pendiente',
  running: 'En curso',
  done: 'Completada',
  blocked: 'Bloqueada',
  error: 'Error',
};

function _on(target: EventTarget, type: string, handler: EventListenerOrEventListenerObject): void {
  target.addEventListener(type, handler);
  _listeners.push({ target, type, handler });
}

function _resolveStageStatus(stage: PipelineStageKey): PipelineStageStatus {
  return _deps?.stageStatuses?.[stage] ?? 'pending';
}

function _buildStageViews(): PipelineStageView[] {
  return PIPELINE_STAGES.map((stage) => ({ ...stage, status: _resolveStageStatus(stage.key) }));
}

function _renderChip(status: PipelineStageStatus): HTMLElement {
  const chip = document.createElement('span');
  chip.className = `pipeline-stage-chip pipeline-stage-chip--${status}`;
  chip.textContent = STATUS_LABELS[status];
  chip.setAttribute('aria-label', `Etapa ${STATUS_LABELS[status].toLowerCase()}`);
  return chip;
}

function _renderPanel(): void {
  if (!_panelEl) return;
  _panelEl.innerHTML = '';
  _panelEl.setAttribute('aria-label', 'Pipeline stages');

  const shell = document.createElement('li');
  shell.className = 'pipeline-panel-shell';

  const panel = document.createElement('section');
  panel.className = 'pipeline-panel';
  panel.setAttribute('aria-readonly', 'true');
  panel.dataset.graphId = _deps?.graphId ?? '';

  const header = document.createElement('header');
  header.className = 'pipeline-panel-header';
  header.innerHTML = `
    <h3 class="pipeline-panel-title">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="6" height="6" rx="1" />
        <rect x="15" y="4" width="6" height="6" rx="1" />
        <rect x="9" y="14" width="6" height="6" rx="1" />
        <path d="M9 7h6M12 10v4" />
      </svg>
      Etapas del pipeline
    </h3>
    <span class="pipeline-panel-badge">Solo lectura</span>
  `;
  panel.appendChild(header);

  const list = document.createElement('ol');
  list.className = 'pipeline-stage-list';
  list.setAttribute('aria-label', 'Pipeline stage status');

  for (const stage of _buildStageViews()) {
    const item = document.createElement('li');
    item.className = `pipeline-stage pipeline-stage--${stage.status}`;
    item.dataset.stage = stage.key;
    item.innerHTML = `
      <span class="pipeline-stage-name">${stage.label}</span>
      <span class="pipeline-stage-meta">${stage.key}</span>
    `;
    item.appendChild(_renderChip(stage.status));
    list.appendChild(item);
  }

  panel.appendChild(list);
  shell.appendChild(panel);
  _panelEl.appendChild(shell);
}

export async function mount(panelEl: HTMLElement, deps: PipelinePanelDeps): Promise<{ refresh: () => Promise<void>; unmount: () => void }> {
  if (!panelEl) return { refresh: async () => {}, unmount: () => {} };

  _panelEl = panelEl;
  _deps = deps;
  _listeners = [];
  _renderPanel();

  return {
    refresh: async () => {
      _renderPanel();
    },
    unmount: () => {
      _listeners.forEach(({ target, type, handler }) => target.removeEventListener(type, handler));
      _listeners = [];
      if (_panelEl) _panelEl.innerHTML = '';
      _panelEl = null;
      _deps = null;
    },
  };
}

export function unmount(): void {
  _listeners.forEach(({ target, type, handler }) => target.removeEventListener(type, handler));
  _listeners = [];
  if (_panelEl) _panelEl.innerHTML = '';
  _panelEl = null;
  _deps = null;
}
