// @ts-nocheck
/**
 * interactions/score-filter.ts
 *
 * Score threshold slider wiring.
 * Design binding: §1.2 — mount(sliderEl, badgeEl, deps) / unmount() shape.
 * No React, no lifecycle library — vanilla TS function with teardown.
 *
 * PR 5: extraction from graph_viewer.html inline script.
 * Ports verbatim: slider 'input' event listener, aria-valuenow/aria-valuetext
 *   update, score badge textContent update.
 *
 * What stays in the template:
 *   - applyVisibility() (combines hiddenTypes + scoreThreshold)
 *   - orphan removal from selection (template-scope state and multi-select panel)
 * These require template-scope dependencies and must NOT be imported here.
 *
 * Deps shape (passed from template via mount()):
 *   onThresholdChange: (threshold: number) => void
 *     — called with the new threshold value; template runs applyVisibility +
 *       orphan removal sequence after receiving it.
 */

// ── Types ──────────────────────────────────────────────────────────────────

export interface ScoreFilterDeps {
  onThresholdChange: (threshold: number) => void;
}

// ── Module state ────────────────────────────────────────────────────────────

let _sliderEl: HTMLInputElement | null = null;
let _badgeEl: HTMLElement | null = null;
let _deps: ScoreFilterDeps | null = null;
let _scoreThreshold: number = 0;
let _listeners: Array<{ el: EventTarget; type: string; fn: EventListener }> = [];

// ── Helpers ─────────────────────────────────────────────────────────────────

function _addListener(el: EventTarget, type: string, fn: EventListener): void {
  el.addEventListener(type, fn);
  _listeners.push({ el, type, fn });
}

// ── Internal ──────────────────────────────────────────────────────────────

/**
 * _applyThreshold — update badge display and slider ARIA attributes.
 * Does NOT call applyVisibility or touch network state — that is the
 * template's responsibility via onThresholdChange.
 */
function _applyThreshold(threshold: number): void {
  _scoreThreshold = threshold;

  if (_badgeEl) {
    _badgeEl.textContent = threshold.toFixed(2);
  }
  if (_sliderEl) {
    _sliderEl.setAttribute("aria-valuenow", threshold.toFixed(2));
    _sliderEl.setAttribute("aria-valuetext", threshold.toFixed(2));
    _sliderEl.value = String(threshold);
  }

  if (_deps) {
    _deps.onThresholdChange(threshold);
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * mount — initialize the score threshold slider wiring.
 *
 * @param sliderEl - The #score-threshold-slider input element.
 * @param badgeEl  - The #score-badge span element.
 * @param deps     - ScoreFilterDeps: { onThresholdChange }
 */
export function mount(
  sliderEl: HTMLInputElement,
  badgeEl: HTMLElement,
  deps: ScoreFilterDeps,
): void {
  _sliderEl = sliderEl;
  _badgeEl = badgeEl;
  _deps = deps;
  _scoreThreshold = 0;
  _listeners = [];

  if (!_sliderEl) return;

  _addListener(_sliderEl, "input", () => {
    const threshold = parseFloat(_sliderEl!.value);
    _applyThreshold(threshold);
  });
}

/**
 * setThreshold — programmatically set the threshold (used by show-all / reset-filters).
 * Updates badge, ARIA attrs, slider value, and fires onThresholdChange.
 */
export function setThreshold(threshold: number): void {
  _applyThreshold(threshold);
}

/**
 * getThreshold — returns the current threshold value.
 */
export function getThreshold(): number {
  return _scoreThreshold;
}

/**
 * unmount — remove all event listeners and clear module state.
 */
export function unmount(): void {
  _listeners.forEach(({ el, type, fn }) => el.removeEventListener(type, fn));
  _listeners = [];
  _sliderEl = null;
  _badgeEl = null;
  _deps = null;
  _scoreThreshold = 0;
}
