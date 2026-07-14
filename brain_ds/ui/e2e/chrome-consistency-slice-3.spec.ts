import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
function viewerHtml() {
  const read = (file: string) => readFileSync(path.join(uiRoot, file), "utf8");
  const color = { background: "#2563eb", dark: "#2563eb", light: "#1d4ed8" };
  return read("templates/graph_viewer.html")
    .split("__BRAIN_DS_TOKENS_CSS__").join(read("static/tokens.css"))
    .split("__VIS_NETWORK_CSS__").join(read("assets/viewer.bundle.css"))
    .split("__VIS_NETWORK_JS__").join(read("assets/viewer.bundle.js"))
    .split("__BRAIN_DS_ICON_SPRITE__").join(read("assets/icons.sprite.svg"))
    .split("__BRAIN_DS_RENDER_CONTEXT__").join(JSON.stringify({ meta: { graph_id: "slice-three" }, nodes: [
      { id: "root", label: "Root", type: "Department", color }, { id: "chosen", label: "Chosen", type: "Department", parent_id: "root", color },
      { id: "leaf", label: "Leaf", type: "Department", parent_id: "chosen", color }, { id: "other", label: "Other", type: "Department", color },
    ], edges: [], type_groups: [], adjacency: {}, detail_index: {} }));
}

test("hierarchy branch history pans and restores in dark and light", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.setContent(viewerHtml(), { waitUntil: "domcontentloaded" });
  await page.locator("#hierarchy-map-toggle").click();
  const close = page.locator("#hierarchy-map-close");
  await page.locator("#hierarchy-map-nodes .hierarchy-node-chip", { hasText: "Other" }).focus();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  const chosen = page.locator("#hierarchy-map-nodes .hierarchy-node-chip", { hasText: "Chosen" });
  await chosen.evaluate((element: HTMLButtonElement) => element.click());
  await expect(page.locator("#hierarchy-map-breadcrumb")).toContainText("Chosen");
  await expect(page.locator("#hierarchy-map-nodes .hierarchy-node-chip", { hasText: "Other" })).toHaveCount(0);
  await page.setViewportSize({ width: 360, height: 640 });
  const scroll = page.locator("#hierarchy-map-scroll");
  await scroll.evaluate((el) => { el.scrollLeft = 42; });
  await page.locator("#hierarchy-map-back").focus();
  await page.locator("#hierarchy-map-back").press("Enter");
  await expect(page.locator("#hierarchy-map-nodes .hierarchy-node-chip", { hasText: "Other" })).toBeVisible();
  await expect(scroll).toHaveJSProperty("scrollLeft", 0);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await scroll.focus();
  await scroll.press("Escape");
  await expect(page.locator("#hierarchy-map")).toBeHidden();
});
