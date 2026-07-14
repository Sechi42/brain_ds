import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const uiRoot = path.resolve(dirname, "..");

function viewerHtml(): string {
  const read = (relative: string) => readFileSync(path.join(uiRoot, relative), "utf8");
  return read("templates/graph_viewer.html")
    .split("__BRAIN_DS_TOKENS_CSS__").join(read("static/tokens.css"))
    .split("__VIS_NETWORK_CSS__").join(read("assets/viewer.bundle.css"))
    .split("__VIS_NETWORK_JS__").join(read("assets/viewer.bundle.js"))
    .split("__BRAIN_DS_ICON_SPRITE__").join(read("assets/icons.sprite.svg"))
    .split("__BRAIN_DS_RENDER_CONTEXT__").join(JSON.stringify({
      meta: { graph_id: "slice-one", org: "Slice One", node_count: 1, edge_count: 0 },
      nodes: [{ id: "node-1", label: "Node one", type: "Department" }],
      edges: [], type_groups: [], adjacency: {}, detail_index: {},
    }));
}

test("toolbar retains essentials and workspace state restores per graph", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.route("http://slice-one.test/", async (route) => {
    await route.fulfill({ contentType: "text/html", body: "<!doctype html><title>Slice one</title>" });
  });
  await page.goto("http://slice-one.test/");
  await page.setContent(viewerHtml(), { waitUntil: "domcontentloaded" });

  const toolbar = page.locator(".top-toolbar");
  const overflow = page.locator('[data-catalog-id="overflow"]');
  const secondary = page.locator("[data-toolbar-secondary]");
  await expect(overflow).toBeVisible();
  await expect(secondary.first()).toBeVisible();

  await page.setViewportSize({ width: 640, height: 800 });
  await expect(overflow).toBeVisible();
  await expect(secondary.first()).toBeHidden();
  expect(await toolbar.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBeTruthy();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.locator(".panel-collapse").click();
  await expect(page.locator(".left-panel-shell")).toHaveClass(/collapsed/);
  await page.locator('[data-rail-icon="filters"]').click();
  await expect(page.locator(".left-panel-shell")).not.toHaveClass(/collapsed/);
  await page.locator('[data-rail-side="right"] [data-rail-icon="inspector"]').click();
  await expect(page.locator(".right-panel-shell")).not.toHaveClass(/collapsed/);

  await page.evaluate(() => {
    const controls = document.querySelector<HTMLElement>(".panel.controls")!;
    const slider = document.querySelector<HTMLInputElement>("#score-threshold-slider")!;
    slider.value = "0.65";
    window.brainDsUI!.workspaceState.capture("graph-a");
    slider.value = "0.10";
    window.brainDsUI!.workspaceState.restore("graph-a");
  });
  await expect(page.locator("#score-threshold-slider")).toHaveValue("0.65");
  await overflow.focus();
  await expect(overflow).toBeFocused();
  const unexpectedErrors = consoleErrors.filter((message) => (
    !message.includes("slice-one.test") && !message.includes("net::ERR_NAME_NOT_RESOLVED")
  ));
  expect(unexpectedErrors).toEqual([]);
});
