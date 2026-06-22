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

function renderStaticTemplate(): string {
  const template = readFileSync(TEMPLATE_PATH, "utf8");
  const tokensCss = readFileSync(TOKENS_PATH, "utf8");
  const viewerCss = readFileSync(BUNDLE_CSS_PATH, "utf8");
  const iconSprite = readFileSync(SPRITE_PATH, "utf8");

  return template
    .split("__BRAIN_DS_TOKENS_CSS__").join(tokensCss)
    .split("__VIS_NETWORK_CSS__").join(viewerCss)
    .split("__BRAIN_DS_ICON_SPRITE__").join(iconSprite)
    .replace(/<script>[\s\S]*?<\/script>/g, "");
}

test("detail panel opens without clipping the selected node header", async ({ page }) => {
  await page.setContent(renderStaticTemplate(), { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: BUNDLE_JS_PATH });

  await page.evaluate(() => {
    const detailEntry = {
      node: { id: "n1", label: "Selected node", type: "Role", supertype: "actor" },
      sections: [
        { title: "Resumen", content: "Purple-ish header card content that should not be clipped at the top.", order: 0, icon: "", accent_color: "#7c3aed" },
        { title: "Notas", content: "The full header and first card should remain visible in the open inspector.", order: 1, icon: "", accent_color: "#7c3aed" },
      ],
      relationships: { incoming: [], outgoing: [] },
      evidence: [],
    };

    window.brainDsUI!.detailPanel.mount(document.getElementById("detail-panel") as HTMLElement, {
      editedDetailIndex: { n1: detailEntry },
      editedData: { nodes: [{ id: "n1", label: "Selected node", type: "Role", supertype: "actor" }] },
      network: { on() {}, selectedNodeIds: new Set<string>(), clearSelection() {} },
      originalNodes: new Map([["n1", { id: "n1", label: "Selected node", type: "Role", supertype: "actor" }]]),
      RENDER_CONTEXT: { nodes: [{ id: "n1", label: "Selected node", type: "Role", supertype: "actor" }], edges: [] },
      adjacency: {},
      motionEnabled: () => false,
    });

    window.brainDsUI!.detailPanel.renderDetailPanel("n1");
  });

  const panel = page.locator("#detail-panel");
  const title = page.locator("#detail-title");
  const card = page.locator("#detail-body .detail-card").first();

  await expect(panel).toBeVisible();
  await expect(title).toHaveText("Selected node");
  await expect(card).toContainText("Purple-ish header card content");

  const panelBox = await panel.boundingBox();
  const titleBox = await title.boundingBox();
  const cardBox = await card.boundingBox();
  if (!panelBox || !titleBox || !cardBox) {
    throw new Error("Missing detail panel bounding boxes");
  }

  expect(titleBox.y).toBeGreaterThan(panelBox.y);
  expect(cardBox.y).toBeGreaterThan(panelBox.y + 80);
  expect(cardBox.height).toBeGreaterThanOrEqual(44);
});

// DDS-3: card_sections with markdown pipe tables MUST render as <table>, not raw | text
test("card_sections markdown pipe tables render as HTML tables not raw pipe characters", async ({ page }) => {
  await page.setContent(renderStaticTemplate(), { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: BUNDLE_JS_PATH });

  await page.evaluate(() => {
    const detailEntry = {
      node: { id: "src-1", label: "Warehouse DB", type: "Data Source", supertype: "data" },
      sections: [
        {
          title: "Columns / Fields",
          content: "| Column | Type | Meaning |\n|---|---|---|\n| id | int | Primary key |",
          order: 1,
          icon: "table",
          accent_color: null,
          is_gap: false,
        },
      ],
      relationships: { incoming: [], outgoing: [] },
      evidence: [],
    };

    window.brainDsUI!.detailPanel.mount(document.getElementById("detail-panel") as HTMLElement, {
      editedDetailIndex: { "src-1": detailEntry },
      editedData: { nodes: [{ id: "src-1", label: "Warehouse DB", type: "Data Source", supertype: "data" }] },
      network: { on() {}, selectedNodeIds: new Set<string>(), clearSelection() {} },
      originalNodes: new Map([["src-1", { id: "src-1", label: "Warehouse DB", type: "Data Source", supertype: "data" }]]),
      RENDER_CONTEXT: { nodes: [{ id: "src-1", label: "Warehouse DB", type: "Data Source", supertype: "data" }], edges: [] },
      adjacency: {},
      motionEnabled: () => false,
    });

    window.brainDsUI!.detailPanel.renderDetailPanel("src-1");
  });

  // DDS-S2: a <table> element must be present (not raw pipe text)
  const table = page.locator("#detail-body table.md-table").first();
  await expect(table).toBeVisible();

  // The raw | characters must NOT appear as plain text
  const body = page.locator("#detail-body");
  const innerText = await body.innerText();
  expect(innerText).not.toContain("| id | int |");

  // Table cells must contain the column data
  const cells = page.locator("#detail-body table.md-table td");
  await expect(cells.first()).toContainText("id");
});
