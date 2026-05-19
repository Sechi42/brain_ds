/**
 * theme-bridge.ts — CSS custom property bridge for the canvas renderer.
 *
 * Single source of truth for reading CSS custom properties into JS.
 * The renderer MUST use these functions rather than calling getComputedStyle
 * directly after migration. (PR2 creates the API; migration happens in later PRs.)
 *
 * Design: §1.2 — pure utility, no side effects on import.
 * No runtime dependencies. No external imports.
 */

/** Token map shape returned by getThemeTokens(). Keys align with renderer._themeTokens. */
export interface ThemeTokens {
  panelBg: string;
  panelText: string;
  panelBorder: string;
  focusRing: string;
  popoverMuted: string;
  marqueeStroke: string;
  marqueeFill: string;
  [key: string]: string;
}

/** Event name for theme-change notifications dispatched on document. */
const THEME_CHANGED_EVENT = "theme-changed";

/**
 * readCssVar — reads a CSS custom property from an element's computed style.
 *
 * Returns `fallback` when:
 *   - getComputedStyle throws (SSR / unit test environment)
 *   - The property value is absent or resolves to whitespace
 *
 * This mirrors the contract in Network.prototype._readCssVar in renderer.ts
 * and is the reference implementation for all later callers.
 *
 * @param element  The element whose computed style is queried.
 * @param name     CSS custom property name, e.g. '--vis-panel-bg'.
 * @param fallback Value returned when the property is unset or unreadable.
 */
export function readCssVar(
  element: Element,
  name: string,
  fallback: string
): string {
  try {
    const value = getComputedStyle(element).getPropertyValue(name);
    if (value && value.trim()) return value.trim();
  } catch (_e) {
    // Silently ignore — e.g. in JSDOM / SSR environments
  }
  return fallback;
}

/**
 * getThemeTokens — resolves all vis-* CSS custom properties used by the renderer.
 *
 * This is the batch version of readCssVar. Later slices will migrate
 * Network.prototype._refreshThemeTokens to call this function.
 *
 * Token names align with those already present in renderer.ts:
 *   --vis-panel-bg, --vis-panel-text, --vis-panel-border,
 *   --vis-focus-ring, --vis-popover-muted, --vis-marquee-stroke, --vis-marquee-fill
 */
export function getThemeTokens(element: Element): ThemeTokens {
  const r = (name: string, fallback: string) => readCssVar(element, name, fallback);
  return {
    panelBg:       r("--vis-panel-bg",       "#1e293b"),
    panelText:     r("--vis-panel-text",      "#e2e8f0"),
    panelBorder:   r("--vis-panel-border",    "#64748b"),
    focusRing:     r("--vis-focus-ring",      "#38bdf8"),
    popoverMuted:  r("--vis-popover-muted",   "#cbd5e1"),
    marqueeStroke: r("--vis-marquee-stroke",  r("--vis-focus-ring", "#38bdf8")),
    marqueeFill:   r("--vis-marquee-fill",    "rgba(56,189,248,0.12)"),
  };
}

/**
 * emitThemeChanged — dispatches a 'theme-changed' CustomEvent on document.
 *
 * The theme toggle in main.ts (and later the theme-toggle button) should call
 * this after switching the data-theme attribute so the renderer can recolor.
 *
 * Using CustomEvent + dispatchEvent rather than a proprietary pub/sub keeps
 * the event model consistent with standard browser patterns.
 */
export function emitThemeChanged(): void {
  if (typeof document === "undefined") return;
  document.dispatchEvent(new CustomEvent(THEME_CHANGED_EVENT, { bubbles: false }));
}

/**
 * subscribeThemeChanged — registers a callback for 'theme-changed' events.
 *
 * Returns an unsubscribe function. Callers (e.g. the Network instance)
 * should call unsubscribe in their cleanup/destroy path.
 *
 * @param callback  Invoked every time emitThemeChanged() is called.
 * @returns         A no-arg function that removes the listener.
 */
export function subscribeThemeChanged(callback: () => void): () => void {
  if (typeof document === "undefined") return () => {};
  const handler = () => callback();
  document.addEventListener(THEME_CHANGED_EVENT, handler);
  return () => document.removeEventListener(THEME_CHANGED_EVENT, handler);
}
