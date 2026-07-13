import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const UI_ROOT = path.resolve(__dirname, "..");
const BUNDLE_JS_PATH = path.join(UI_ROOT, "assets", "viewer.bundle.js");
const TEMPLATE_PATH = path.join(UI_ROOT, "templates", "graph_viewer.html");
const TOKENS_PATH = path.join(UI_ROOT, "static", "tokens.css");
const BUNDLE_CSS_PATH = path.join(UI_ROOT, "assets", "viewer.bundle.css");
const SPRITE_PATH = path.join(UI_ROOT, "assets", "icons.sprite.svg");

interface SecretHandle {
  handle: string;
  kind: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

// Mirrors detail-panel-chrome.spec.ts: inline the template + bundled CSS so the
// detail panel renders with real chrome styles, with the inline <script> stripped.
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

// ── B1: binding a candidate secret creates an unvalidated lifecycle binding ──
test("bind action creates a lifecycle binding and confirms validation is required", async ({ page }) => {
  await page.setContent('<section id="secret-panel"></section>', { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: BUNDLE_JS_PATH });

  await page.evaluate(async () => {
    const stored: SecretHandle[] = [
      {
        handle: "warehouse/prod",
        kind: "aws-postgres",
        created_at: "2026-06-15T10:00:00Z",
        metadata: { database: "orders" },
      },
    ];
    const calls: Array<{ url: string; method?: string; body?: Record<string, unknown> }> = [];
    (window as typeof window & { __secretApiCalls?: typeof calls }).__secretApiCalls = calls;
    const boundEvents: Array<{ sourceId: string; descriptor: Record<string, unknown> }> = [];
    (window as typeof window & { __boundEvents?: typeof boundEvents }).__boundEvents = boundEvents;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, method, body });

      if (url.includes("/api/secrets/schema")) {
        return new Response(JSON.stringify({ schema_version: "1.0", provider_kinds: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/source-connections/candidates")) {
        return new Response(JSON.stringify({
          status: "ok",
          secrets: [{
            secret_ref: "sec_opaque_orders_candidate",
            provider_kind: "aws-postgres",
            validation_status: "unbound",
            required_provider_inputs: ["spreadsheet_ref"],
          }],
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/source-connections/bind") && method === "POST") {
        return new Response(JSON.stringify({
          status: "ok",
          binding: {
            secret_ref: "sec_opaque_orders_candidate",
            provider_kind: "aws-postgres",
            validation_status: "unvalidated",
            documentation_status: "not_started",
            writeback_status: "idle",
            provider_inputs: { spreadsheet_ref: "graph-source-ds-orders" },
          },
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ handles: stored }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    await window.brainDsUI!.secretPanel.mount(document.getElementById("secret-panel") as HTMLElement, {
      graphId: "demo-graph",
      dataSources: [{ id: "ds-orders", label: "Orders warehouse", kind: "Data Source" }],
      onBound: (sourceId: string, descriptor: Record<string, unknown>) => {
        boundEvents.push({ sourceId, descriptor });
      },
    } as Parameters<typeof window.brainDsUI.secretPanel.mount>[1]);
  });

  // The bind row renders for the workspace handle because a Data Source was provided.
  const select = page.locator(".secret-bind-select").first();
  const bindBtn = page.locator(".secret-bind-btn").first();
  await expect(select).toBeVisible();
  await select.selectOption("ds-orders");
  await bindBtn.click();

  // Success badge confirms the lifecycle requires validation before documentation.
  const badge = page.locator(".secret-bind-badge--ok").first();
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText("Binding created. Validate before documentation.");

  // A compatible opaque candidate reference is resolved before the bind request.
  const calls = await page.evaluate(
    () =>
      (window as typeof window & {
        __secretApiCalls?: Array<{ url: string; method?: string; body?: Record<string, unknown> }>;
      }).__secretApiCalls || [],
  );
  const candidates = calls.find((c) => c.method === "GET" && c.url.includes("/api/source-connections/candidates"));
  expect(candidates).toBeTruthy();
  const bind = calls.find((c) => c.method === "POST" && c.url.includes("/api/source-connections/bind"));
  expect(bind).toBeTruthy();
  expect(bind?.body?.source_node_id).toBe("ds-orders");
  expect(bind?.body?.secret_ref).toBe("sec_opaque_orders_candidate");
  expect(bind?.body?.provider_inputs).toEqual({ spreadsheet_ref: "graph-source-ds-orders" });

  // onBound receives only the current lifecycle projection, never a secret handle.
  const bound = await page.evaluate(
    () =>
      (window as typeof window & {
        __boundEvents?: Array<{ sourceId: string; descriptor: Record<string, unknown> }>;
      }).__boundEvents || [],
  );
  expect(bound.length).toBe(1);
  expect(bound[0]?.sourceId).toBe("ds-orders");
  expect(bound[0]?.descriptor).toEqual({ validation_status: "unvalidated", provider_kind: "aws-postgres" });
});

// ── B3: an unvalidated lifecycle binding is not yet explorable ─────────────────
test("detail panel keeps an unvalidated Data Source out of the explorable state", async ({ page }) => {
  await page.setContent(renderStaticTemplate(), { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: BUNDLE_JS_PATH });

  await page.evaluate(() => {
    const node = {
      id: "ds-orders",
      label: "Orders warehouse",
      type: "Data Source",
      details: {
        secret_binding: {
          provider_kind: "aws-postgres",
          validation_status: "unvalidated",
          documentation_status: "not_started",
          writeback_status: "idle",
        },
      },
    };
    const detailEntry = {
      node,
      sections: [
        { title: "Resumen", content: "Orders warehouse data source.", order: 0, icon: "", accent_color: "#7c3aed" },
      ],
      relationships: { incoming: [], outgoing: [] },
      evidence: [],
    };

    window.brainDsUI!.detailPanel.mount(document.getElementById("detail-panel") as HTMLElement, {
      editedDetailIndex: { "ds-orders": detailEntry },
      editedData: { nodes: [node] },
      network: { on() {}, selectedNodeIds: new Set<string>(), clearSelection() {} },
      originalNodes: new Map([["ds-orders", node]]),
      RENDER_CONTEXT: { nodes: [node], edges: [] },
      adjacency: {},
      motionEnabled: () => false,
    });

    window.brainDsUI!.detailPanel.renderDetailPanel("ds-orders");
  });

  const badge = page.locator(".detail-explorable-badge");
  await expect(badge).toHaveCount(0);
  const lifecycle = page.locator(".source-lifecycle-card");
  await expect(lifecycle).toContainText("binding state: bound");
  await expect(lifecycle).toContainText("validation status: unvalidated");
});
