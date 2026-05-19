/**
 * motion.ts — prefers-reduced-motion utility module.
 *
 * Single source of truth for querying and subscribing to the
 * `prefers-reduced-motion: reduce` media feature from JS code.
 *
 * Design: §1.2 — pure utility, no side effects on import.
 * No runtime dependencies. No external imports.
 *
 * NOTE (PR2): The Network class in renderer.ts still contains its own
 * _bindReducedMotion and motionEnabled. Migration of those call sites to
 * use this module is deferred to the motion microinteractions PR (Slice 8).
 * This module establishes the future API surface.
 */

/** The exact media query string used for reduced-motion detection. */
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * motionEnabled — returns true when the user has NOT requested reduced motion.
 *
 * Safe default: returns true (motion allowed) when matchMedia is unavailable
 * (e.g. in JSDOM / SSR environments), so the renderer never gets stuck in a
 * static-only mode without the user actually requesting it.
 *
 * Mirrors Network.prototype.motionEnabled() in renderer.ts.
 */
export function motionEnabled(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return true; // Safe default: motion allowed when API unavailable
  }
  return !window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/**
 * subscribeReducedMotion — registers a callback that fires when the
 * prefers-reduced-motion preference changes.
 *
 * Returns an unsubscribe function. Callers should invoke it in their
 * cleanup/destroy path to avoid listener leaks.
 *
 * Handles both the modern addEventListener API and the legacy addListener
 * fallback for browser compatibility (mirrors renderer.ts _bindReducedMotion).
 *
 * @param callback  Invoked with the new `motionEnabled` value (boolean) on change.
 * @returns         A no-arg function that removes the listener.
 */
export function subscribeReducedMotion(callback: (enabled: boolean) => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }

  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  const handler = (event: MediaQueryListEvent | MediaQueryList) => {
    callback(!event.matches);
  };

  // Prefer modern addEventListener; fall back to deprecated addListener
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", handler as (e: MediaQueryListEvent) => void);
    return () => query.removeEventListener("change", handler as (e: MediaQueryListEvent) => void);
  } else if (typeof (query as MediaQueryList & { addListener?: Function }).addListener === "function") {
    // Legacy path — addListener (deprecated but still in some environments)
    (query as unknown as { addListener: Function }).addListener(handler);
    return () => {
      (query as unknown as { removeListener: Function }).removeListener(handler);
    };
  }

  return () => {};
}
