import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const UI_ROOT = path.resolve(__dirname, "..");
const TEMPLATE_PATH = path.join(UI_ROOT, "templates", "graph_viewer.html");
const TOKENS_PATH = path.join(UI_ROOT, "static", "tokens.css");
const BUNDLE_CSS_PATH = path.join(UI_ROOT, "assets", "viewer.bundle.css");
const BUNDLE_JS_PATH = path.join(UI_ROOT, "assets", "viewer.bundle.js");
const SPRITE_PATH = path.join(UI_ROOT, "assets", "icons.sprite.svg");

function renderInteractiveHtml(context: Record<string, unknown>): string {
  const template = readFileSync(TEMPLATE_PATH, "utf8");
  const tokensCss = readFileSync(TOKENS_PATH, "utf8");
  const viewerCss = readFileSync(BUNDLE_CSS_PATH, "utf8");
  const viewerJs = readFileSync(BUNDLE_JS_PATH, "utf8");
  const iconSprite = readFileSync(SPRITE_PATH, "utf8");
  const meta = {
    graph_id: "demo-graph",
    status_label: "LIVE",
    ...(context.meta as Record<string, unknown> | undefined),
  };

  return template
    .split("__BRAIN_DS_TOKENS_CSS__").join(tokensCss)
    .split("__BRAIN_DS_RENDER_CONTEXT__").join(JSON.stringify({ ...context, meta }))
    .split("__VIS_NETWORK_CSS__").join(viewerCss)
    .split("__VIS_NETWORK_JS__").join(viewerJs)
    .split("__BRAIN_DS_ICON_SPRITE__").join(iconSprite);
}

async function mountCheckpoint(page: import("@playwright/test").Page): Promise<void> {
  const html = renderInteractiveHtml({
    graph_id: "demo-graph",
    nodes: [
      {
        id: "source-node",
        label: "Source Node",
        modified_at: "2026-06-15T10:00:00Z",
      },
    ],
    edges: [],
    detail_index: {},
  });

  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    window.fetch = async () => new Response(JSON.stringify({ nodes: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

test("pipeline panel renders six pending stages in the rail", async ({ page }) => {
  await mountCheckpoint(page);

  const pipelineIcon = page.locator('[data-rail-icon="pipeline"]');
  const pipelinePanel = page.locator("#ai-actions-receipts");

  await page.locator(".panel-collapse-right").click();
  await expect(page.locator(".right-panel-shell")).not.toHaveClass(/collapsed/);

  await pipelineIcon.click();
  await expect(page.locator("#detail-panel")).toHaveAttribute("hidden", "");
  await expect(page.locator("#brd-panel")).toHaveAttribute("hidden", "");
  await expect(page.locator("#secret-panel")).toHaveAttribute("hidden", "");

  const stages = page.locator("#ai-actions-receipts li.pipeline-stage");
  await expect(stages).toHaveCount(6);
  await expect(page.locator(".pipeline-panel")).toBeVisible();

  for (const stage of ["Setup", "Intake", "Map", "BRD", "Verify", "Archive"]) {
    await expect(pipelinePanel).toContainText(stage);
  }
  await expect(page.locator(".pipeline-stage-chip--pending")).toHaveCount(6);
  await expect(page.locator("#ai-actions-receipts button")).toHaveCount(0);
  await expect(page.locator(".pipeline-panel")).toHaveAttribute("aria-readonly", "true");

  await page.screenshot({ path: "test-results/pipeline-panel-checkpoint.png", fullPage: false });
});
