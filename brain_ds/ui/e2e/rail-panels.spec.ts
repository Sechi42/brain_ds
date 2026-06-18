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
  const brdMarkdown = "Status: COMPLETE\nOrganization: Demo Org\n\n## Executive Summary\n\nOwner: [[Fleet Manager]]";
  const html = renderInteractiveHtml({
    graph_id: "demo-graph",
    nodes: [
      {
        id: "brd-demo-graph",
        label: "BRD",
        modified_at: "2026-02-03T10:15:00Z",
        card_sections: [
          { title: "Contenido", content: brdMarkdown, order: 0, icon: "" },
        ],
      },
      {
        id: "demo-role-fleet-manager",
        label: "Fleet Manager",
        modified_at: "2026-02-01T00:00:00Z",
      },
      {
        id: "warehouse-source",
        label: "Warehouse Source",
        type: "Data Source",
        modified_at: "2026-02-02T00:00:00Z",
      },
      {
        id: "warehouse-ops-node",
        label: "Warehouse Ops Node",
        modified_at: "2026-02-02T02:00:00Z",
      },
      {
        id: "detail-node",
        label: "Very long selected node header that should stay fully readable",
        type: "Role",
        supertype: "actor",
        modified_at: "2026-02-03T13:30:00Z",
      },
    ],
    edges: [
      { source: "warehouse-source", target: "warehouse-ops-node", label: "feeds", weight: 0.8 },
      { source: "detail-node", target: "warehouse-source", label: "uses", weight: 0.7 },
    ],
    detail_index: {
      "brd-demo-graph": {
        id: "brd-demo-graph",
        label: "BRD",
        sections: [
          { title: "Contenido", content: brdMarkdown, order: 0, icon: "" },
        ],
      },
      "demo-role-fleet-manager": {
        id: "demo-role-fleet-manager",
        label: "Fleet Manager",
        sections: [
          { title: "Resumen", content: "Purple-ish header card content that should not be clipped at the top.", order: 0, icon: "", accent_color: "#7c3aed" },
          { title: "Notas", content: "The full header and first card should remain visible in the open inspector.", order: 1, icon: "", accent_color: "#7c3aed" },
        ],
      },
      "detail-node": {
        id: "detail-node",
        label: "Very long selected node header that should stay fully readable",
        sections: [
          { title: "Resumen", content: "Purple-ish header card content that should not be clipped at the top.", order: 0, icon: "", accent_color: "#7c3aed" },
          { title: "Notas", content: "The full header and first card should remain visible in the open inspector.", order: 1, icon: "", accent_color: "#7c3aed" },
        ],
      },
    },
    adjacency: {
      "warehouse-source": ["warehouse-ops-node"],
      "detail-node": ["warehouse-source"],
    },
  });

  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({ content: ".secret-panel[hidden] { display: flex !important; }" });

  await page.evaluate(() => {
    const schema = {
      schema_version: "1.0",
      provider_kinds: {
        postgres: {
          required: ["host", "port", "database", "username", "sslmode"],
          types: {
            host: "string",
            port: "integer",
            database: "string",
            username: "string",
            sslmode: "string",
          },
        },
      },
    };

    const secretHandles = [
      {
        handle: "warehouse_ro",
        kind: "postgres",
        created_at: "2026-06-15T10:00:00Z",
        metadata: {
          host: "db.local",
          port: 5432,
          database: "warehouse",
          username: "etl",
          sslmode: "require",
          secret_ref: "***",
        },
      },
    ];

    const nodeRows = [
      {
        id: "brd-demo-graph",
        label: "BRD",
        modified_at: "2026-02-03T10:15:00Z",
        card_sections: [
          { title: "Contenido", content: "Status: COMPLETE", order: 0, icon: "" },
        ],
      },
      {
        id: "demo-role-fleet-manager",
        label: "Fleet Manager",
        modified_at: "2026-02-01T00:00:00Z",
      },
    ];

    const getJsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = String(init?.method || "GET").toUpperCase();

      if (url.includes("/api/secrets/schema")) {
        return getJsonResponse(schema);
      }
      if (url.includes("/api/secrets") && method === "GET") {
        return getJsonResponse({ handles: secretHandles });
      }
      if (url.includes("/api/secrets") && method === "POST") {
        const body = JSON.parse(String(init?.body || "{}"));
        secretHandles.push({
          handle: body.handle,
          kind: body.kind,
          created_at: "2026-06-15T12:00:00Z",
          metadata: body.metadata,
        });
        return getJsonResponse({ handle: body.handle, created_at: "2026-06-15T12:00:00Z" }, 201);
      }
      if (url.includes("/api/secrets/") && method === "DELETE") {
        const handle = decodeURIComponent(url.split("?")[0]?.split("/").pop() || "");
        for (let i = secretHandles.length - 1; i >= 0; i -= 1) {
          if (secretHandles[i].handle === handle) secretHandles.splice(i, 1);
        }
        return new Response(null, { status: 204 });
      }
      return getJsonResponse({ nodes: nodeRows });
    };
  });
}

test("right rail panels stay exclusive, isolated, and bounded", async ({ page }) => {
  await mountCheckpoint(page);

  const brdIcon = page.locator('[data-rail-icon="brd"]');
  const settingsIcon = page.locator('[data-rail-icon="settings"]');
  const inspectorIcon = page.locator('[data-rail-icon="inspector"]');
  const brdPanel = page.locator("#brd-panel");
  const secretPanel = page.locator("#secret-panel");
  const inspectorStub = page.locator(".inspector-stub-scroll");
  const rightShell = page.locator(".right-panel-shell");

  await brdIcon.click();
  await expect(brdPanel).toBeVisible();
  await expect(secretPanel).toHaveAttribute("hidden", "");
  await expect(inspectorStub).toHaveAttribute("hidden", "");

  for (const selector of ["#brd-panel", "#secret-panel", ".inspector-stub-scroll"]) {
    const panel = page.locator(selector);
    await expect(panel).toHaveCSS("isolation", "isolate");
    await expect(panel).toHaveCSS("contain", /layout/);
  }

  await settingsIcon.click();
  await expect(secretPanel).toBeVisible();
  await expect(brdPanel).toHaveAttribute("hidden", "");
  await expect(inspectorStub).toHaveAttribute("hidden", "");
  await expect(secretPanel).toHaveCSS("display", "flex");

  const secretBox = await secretPanel.boundingBox();
  const shellBox = await rightShell.boundingBox();
  if (!secretBox || !shellBox) {
    throw new Error("Missing bounding boxes for right-rail checkpoint");
  }
  expect(secretBox.width).toBeLessThanOrEqual(360);
  expect(secretBox.height).toBeLessThan(shellBox.height);

  await inspectorIcon.click();
  await expect(brdPanel).toHaveAttribute("hidden", "");
  await expect(secretPanel).toHaveAttribute("hidden", "");
  await expect(inspectorStub).not.toHaveAttribute("hidden", "");
  await expect(secretPanel).toHaveCSS("display", "none");

  await page.screenshot({ path: "test-results/rail-panels-checkpoint.png", fullPage: false });
});

test("panel chrome gains breathing room and distinct selected states", async ({ page }) => {
  await mountCheckpoint(page);

  const settingsIcon = page.locator('[data-rail-icon="settings"]');
  const inspectorIcon = page.locator('[data-rail-icon="inspector"]');
  const aiActionsIcon = page.locator('[data-rail-icon="ai-actions"]');
  const datasourceBtn = page.locator('#projects-grouping [data-group-by="datasource"]');
  const datasourceGroup = page.locator('#projects-panel .project-group[data-group-by="datasource"]');
  const secretPanel = page.locator('#secret-panel');

  await datasourceBtn.click();
  await expect(datasourceGroup.first()).toBeVisible();
  await datasourceGroup.first().locator('summary').click();
  const datasourceRow = datasourceGroup.first().locator('.project-node-row').first();
  const datasourceRowBox = await datasourceRow.boundingBox();
  if (!datasourceRowBox) {
    throw new Error('Missing datasource row bounding box');
  }
  expect(datasourceRowBox.height).toBeGreaterThanOrEqual(44);

  await settingsIcon.click();
  await expect(secretPanel).toBeVisible();
  await expect(secretPanel).toHaveCSS('margin-top', '16px');
  await expect(page.locator('.secret-list')).toHaveCSS('padding-left', '16px');
  await expect(page.locator('.secret-form')).toHaveCSS('padding-left', '16px');

  await inspectorIcon.evaluate((el) => el.setAttribute('aria-selected', 'true'));
  await aiActionsIcon.evaluate((el) => el.setAttribute('aria-selected', 'true'));
  const inspectorSelectedShadow = await inspectorIcon.evaluate((el) => getComputedStyle(el).boxShadow);
  const aiSelectedShadow = await aiActionsIcon.evaluate((el) => getComputedStyle(el).boxShadow);
  expect(inspectorSelectedShadow).not.toBe(aiSelectedShadow);
});
