export type TypeColor = string | { background?: string; dark?: string; light?: string } | undefined;

export function resolveTypeColor(color: TypeColor): { dark: string; light: string } {
  if (typeof color === "string") return { dark: color, light: color };
  return {
    dark: color?.dark || color?.background || color?.light || "",
    light: color?.light || color?.dark || color?.background || "",
  };
}

export function applyTypeColor(el: HTMLElement | null | undefined, color: TypeColor): void {
  if (!el?.style || typeof el.style.setProperty !== "function") return;
  const resolved = resolveTypeColor(color);
  if (resolved.dark) el.style.setProperty("--type-color-dark", resolved.dark);
  if (resolved.light) el.style.setProperty("--type-color-light", resolved.light);
}
