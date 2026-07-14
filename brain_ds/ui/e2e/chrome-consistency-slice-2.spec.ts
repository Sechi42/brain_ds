import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(dirname, "..");

function viewerHtml() {
  const read = (relative: string) => readFileSync(path.join(uiRoot, relative), "utf8");
  const colors = { Department: { background: "#2563eb", dark: "#2563eb", light: "#1d4ed8" }, Unknown: { background: "#6b7280", dark: "#6b7280", light: "#4b5563" } };
  return read("templates/graph_viewer.html")
    .split("__BRAIN_DS_TOKENS_CSS__").join(read("static/tokens.css"))
    .split("__VIS_NETWORK_CSS__").join(read("assets/viewer.bundle.css"))
    .split("__VIS_NETWORK_JS__").join(read("assets/viewer.bundle.js"))
    .split("__BRAIN_DS_ICON_SPRITE__").join(read("assets/icons.sprite.svg"))
    .split("__BRAIN_DS_RENDER_CONTEXT__").join(JSON.stringify({
      meta: { graph_id: "slice-two", org: "Slice Two", node_count: 2, edge_count: 0 },
      nodes: [{ id: "d", label: "Department", type: "Department", color: colors.Department }, { id: "u", label: "Legacy", type: "Unknown", color: colors.Unknown }],
      edges: [], type_groups: [{ supertype: "actor", types: [{ type: "Department", count: 1, color: colors.Department }, { type: "Unknown", count: 1, color: colors.Unknown }] }], adjacency: {}, detail_index: {},
    }));
}

test("compact legend mirrors filter visibility and themed node colors", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.setViewportSize({ width: 360, height: 640 });
  await page.route("http://slice-two.test/", (route) => route.fulfill({ contentType: "text/html", body: "<!doctype html>" }));
  await page.goto("http://slice-two.test/");
  await page.setContent(viewerHtml(), { waitUntil: "domcontentloaded" });

  const toggle = page.locator("#canvas-legend-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeVisible();
  await toggle.focus();
  await expect(toggle).toBeFocused();
  await toggle.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const legendItem = page.locator(".canvas-legend-item").first();
  await expect(legendItem).toHaveAttribute("aria-pressed", "true");
  expect(await legendItem.evaluate((el) => el.getBoundingClientRect().right <= window.innerWidth)).toBeTruthy();
  await legendItem.focus();
  await legendItem.press("Enter");
  await expect(legendItem).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".filter-checkbox").first()).not.toBeChecked();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(legendItem.locator(".chip")).toHaveCSS("--type-color-light", "#1d4ed8");
  expect(consoleErrors.filter((message) => !message.includes("slice-two.test") && !message.includes("ERR_NAME_NOT_RESOLVED"))).toEqual([]);
});

test("legend controls use Spanish accessible copy and the detail fallback icon is bundled", async ({ page }) => {
  await page.setContent(viewerHtml(), { waitUntil: "domcontentloaded" });

  const toggle = page.locator("#canvas-legend-toggle");
  await expect(toggle).toHaveAttribute("title", "Mostrar u ocultar leyenda de colores");
  await expect(page.locator("#canvas-legend-list")).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator("#icon-file-text")).toHaveCount(1);

  await toggle.press("Enter");
  const legendItem = page.locator(".canvas-legend-item").first();
  await expect(legendItem).toHaveAttribute("aria-label", "Alternar visibilidad de Department");
  await expect(page.locator(".canvas-legend-item").nth(1)).toHaveAttribute("aria-label", "Alternar visibilidad de Unknown");
});
