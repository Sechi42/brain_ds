const SESSION_KEY = "brain_ds.workspace-state.v1";

interface WorkspaceSnapshot {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  railWidth: string;
  inspectorWidth: string;
  activeLeftRail: string | null;
  controlsScrollTop: number;
  details: Record<string, boolean>;
  controls: Record<string, string>;
}

type StoredWorkspaceState = Record<string, WorkspaceSnapshot>;

function readAll(): StoredWorkspaceState {
  try {
    const value = sessionStorage.getItem(SESSION_KEY);
    const parsed = value ? JSON.parse(value) : {};
    return parsed && typeof parsed === "object" ? parsed as StoredWorkspaceState : {};
  } catch (_error) {
    return {};
  }
}

function writeAll(state: StoredWorkspaceState): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
  } catch (_error) {
    // Storage is optional; the current workspace remains usable without it.
  }
}

function namedControls(root: ParentNode): Record<string, string> {
  const values: Record<string, string> = {};
  root.querySelectorAll<HTMLInputElement | HTMLButtonElement>("input[id], button[id]").forEach((control) => {
    const id = control.id;
    if (!id) return;
    if (control instanceof HTMLInputElement) values[id] = control.value;
    else if (control.hasAttribute("aria-checked")) values[id] = control.getAttribute("aria-checked") || "false";
    else if (control.hasAttribute("aria-pressed")) values[id] = control.getAttribute("aria-pressed") || "false";
  });
  return values;
}

export function capture(graphId: string): void {
  if (!graphId) return;
  const shell = document.querySelector<HTMLElement>(".workspace-shell");
  const left = document.querySelector<HTMLElement>(".left-panel-shell");
  const right = document.querySelector<HTMLElement>(".right-panel-shell");
  const controlsRoot = document.querySelector<HTMLElement>(".panel.controls");
  if (!shell || !left || !right || !controlsRoot) return;

  const details: Record<string, boolean> = {};
  document.querySelectorAll<HTMLDetailsElement>("details[data-accordion-section]").forEach((detail) => {
    const name = detail.getAttribute("data-accordion-section");
    if (name) details[name] = detail.open;
  });

  const activeLeftRail = document.querySelector<HTMLElement>("[data-rail-side='left'] [data-rail-icon][aria-selected='true']");
  const state = readAll();
  state[graphId] = {
    leftCollapsed: left.classList.contains("collapsed"),
    rightCollapsed: right.classList.contains("collapsed"),
    railWidth: shell.dataset.railW || "288px",
    inspectorWidth: shell.dataset.inspectorW || "352px",
    activeLeftRail: activeLeftRail?.getAttribute("data-rail-icon") || null,
    controlsScrollTop: controlsRoot.scrollTop,
    details,
    controls: namedControls(document),
  };
  writeAll(state);
}

export function restore(graphId: string): boolean {
  if (!graphId) return false;
  const snapshot = readAll()[graphId];
  if (!snapshot) return false;
  const shell = document.querySelector<HTMLElement>(".workspace-shell");
  const left = document.querySelector<HTMLElement>(".left-panel-shell");
  const right = document.querySelector<HTMLElement>(".right-panel-shell");
  const controlsRoot = document.querySelector<HTMLElement>(".panel.controls");
  if (!shell || !left || !right || !controlsRoot) return false;

  shell.dataset.railW = snapshot.railWidth;
  shell.dataset.inspectorW = snapshot.inspectorWidth;
  left.classList.toggle("collapsed", snapshot.leftCollapsed);
  right.classList.toggle("collapsed", snapshot.rightCollapsed);
  shell.style.setProperty("--rail-w", snapshot.leftCollapsed ? "0px" : snapshot.railWidth);
  shell.style.setProperty("--inspector-w", snapshot.rightCollapsed ? "0px" : snapshot.inspectorWidth);

  document.querySelectorAll<HTMLDetailsElement>("details[data-accordion-section]").forEach((detail) => {
    const name = detail.getAttribute("data-accordion-section");
    if (name && Object.prototype.hasOwnProperty.call(snapshot.details, name)) detail.open = Boolean(snapshot.details[name]);
  });
  Object.entries(snapshot.controls).forEach(([id, value]) => {
    const control = document.getElementById(id) as HTMLInputElement | HTMLButtonElement | null;
    if (!control) return;
    if (control instanceof HTMLInputElement) control.value = value;
    else if (control.hasAttribute("aria-checked")) control.setAttribute("aria-checked", value);
    else if (control.hasAttribute("aria-pressed")) control.setAttribute("aria-pressed", value);
  });
  controlsRoot.scrollTop = snapshot.controlsScrollTop;
  return true;
}
