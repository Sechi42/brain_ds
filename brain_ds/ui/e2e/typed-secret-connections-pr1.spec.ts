// typed-secret-connections PR1 — Accordion Split + Per-Row Secret Probe Button
//
// TDD: tests MUST fail before implementation. These cover:
//   PR1-T1: accordion sections are distinct DOM nodes
//   PR1-T2: clicking one section doesn't toggle the other
//   PR1-T3/T4/T5: probe button per secret row + inline status badge

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
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

// ── Shared render helper (mirrors rail-panels.spec.ts pattern) ──────────────

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

async function mountGraphViewer(page: import("@playwright/test").Page): Promise<void> {
  const html = renderInteractiveHtml({
    graph_id: "demo-graph",
    nodes: [
      { id: "node-a", label: "Node A", modified_at: "2026-06-20T10:00:00Z" },
    ],
    edges: [],
    detail_index: {},
  });
  await page.setContent(html, { waitUntil: "domcontentloaded" });
}

// ── Secret panel mount helper (mirrors secret-panel.spec.ts pattern) ────────

interface SecretHandle {
  handle: string;
  kind: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

async function mountSecretPanelWithProbe(
  page: import("@playwright/test").Page,
  handles: SecretHandle[],
  validateResponses: Record<string, { status: string; connection: string; message: string }> = {},
): Promise<void> {
  await page.setContent('<section id="secret-panel"></section>', { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: bundlePath });
  await page.evaluate(
    async ({ handles, validateResponses }) => {
      const schema = {
        schema_version: "1.0",
        provider_kinds: {
          "aws-postgres": {
            required: ["secret_id", "database"],
            types: { region: "string", secret_id: "string", database: "string" },
            requires_raw_value: false,
            descriptions: {
              region: "AWS region (default: us-east-2)",
              secret_id: "Secret Manager ARN or name",
              database: "Database name (from handle metadata)",
            },
            placeholders: { region: "us-east-2", secret_id: "arn:aws:secretsmanager:...", database: "my_db" },
          },
          "mock-postgres": {
            required: ["host", "port"],
            types: { host: "string", port: "integer" },
            requires_raw_value: true,
          },
        },
      };

      let stored = [...handles];
      (window as typeof window & { __secretHandles?: typeof stored }).__secretHandles = stored;
      const validateCalls: string[] = [];
      (window as typeof window & { __validateCalls?: typeof validateCalls }).__validateCalls = validateCalls;

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method || "GET").toUpperCase();

        if (url.includes("/api/secrets/schema")) {
          return new Response(JSON.stringify(schema), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/secrets/validate")) {
          // POST /api/secrets/validate?handle=xxx
          const params = new URLSearchParams(url.split("?")[1] || "");
          const handle = params.get("handle") || "";
          validateCalls.push(handle);
          const resp = validateResponses[handle] || { status: "ok", connection: "probed", message: "Conexión exitosa." };
          return new Response(JSON.stringify(resp), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/secrets") && method === "POST") {
          const body = JSON.parse(String(init?.body || "{}"));
          stored.push({ handle: body.handle, kind: body.kind, created_at: "2026-06-20T12:00:00Z", metadata: body.metadata });
          return new Response(JSON.stringify({ handle: body.handle, created_at: "2026-06-20T12:00:00Z" }), { status: 201, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/secrets/") && method === "DELETE") {
          const p = url.split("?")[0] || "";
          const handle = decodeURIComponent(p.split("/").pop() || "");
          stored = stored.filter((h) => h.handle !== handle);
          return new Response(null, { status: 204 });
        }
        return new Response(JSON.stringify({ handles: stored, status: "ready" }), { status: 200, headers: { "Content-Type": "application/json" } });
      };

      const handle = await window.brainDsUI!.secretPanel.mount(
        document.getElementById("secret-panel") as HTMLElement,
        { graphId: "demo-graph" },
      );
      (window as typeof window & { __secretPanelHandle?: typeof handle }).__secretPanelHandle = handle;
    },
    { handles, validateResponses },
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PR1-T1 / PR1-T2 — Accordion split tests (WILL FAIL before PR1-T2 implementation)
// ══════════════════════════════════════════════════════════════════════════════

test("accordion: ai-actions and pipeline are distinct DOM nodes", async ({ page }) => {
  await mountGraphViewer(page);

  const aiActionsSection = page.locator('[data-accordion-section="ai-actions"]');
  const pipelineSection = page.locator('[data-accordion-section="pipeline"]');

  // Both selectors MUST resolve — and to different elements
  await expect(aiActionsSection).toHaveCount(1);
  await expect(pipelineSection).toHaveCount(1);

  // Verify they are distinct elements (not the same node)
  const sameNode = await page.evaluate(() => {
    const ai = document.querySelector('[data-accordion-section="ai-actions"]');
    const pipeline = document.querySelector('[data-accordion-section="pipeline"]');
    return ai === pipeline;
  });
  expect(sameNode).toBe(false);
});

test("accordion: rail icons are EXCLUSIVE tabs — clicking pipeline hides ai-actions and vice versa", async ({ page }) => {
  await mountGraphViewer(page);

  const aiActionsIcon = page.locator('[data-rail-icon="ai-actions"]');
  const pipelineIcon = page.locator('[data-rail-icon="pipeline"]');
  const aiActionsSection = page.locator('[data-accordion-section="ai-actions"]');
  const pipelineSection = page.locator('[data-accordion-section="pipeline"]');

  // Click AI actions: its section is shown+open, pipeline is hidden.
  await aiActionsIcon.click();
  expect(await aiActionsSection.evaluate((el) => (el as HTMLDetailsElement).hidden)).toBe(false);
  expect(await aiActionsSection.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(true);
  expect(await pipelineSection.evaluate((el) => (el as HTMLDetailsElement).hidden)).toBe(true);

  // Click pipeline: now pipeline is shown+open and ai-actions is HIDDEN.
  // (Before the fix both stayed visible in the same panel — the reported bug.)
  await pipelineIcon.click();
  expect(await pipelineSection.evaluate((el) => (el as HTMLDetailsElement).hidden)).toBe(false);
  expect(await pipelineSection.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(true);
  expect(await aiActionsSection.evaluate((el) => (el as HTMLDetailsElement).hidden)).toBe(true);
});

test("accordion: pipeline section is separate details element from ai-actions", async ({ page }) => {
  await mountGraphViewer(page);

  // Both must be <details> elements
  const aiTag = await page.locator('[data-accordion-section="ai-actions"]').evaluate((el) => el.tagName.toLowerCase());
  const pipeTag = await page.locator('[data-accordion-section="pipeline"]').evaluate((el) => el.tagName.toLowerCase());
  expect(aiTag).toBe("details");
  expect(pipeTag).toBe("details");

  // Toggling one must not affect the other
  await page.locator('[data-accordion-section="pipeline"]').evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  const aiStillClosed = await page.locator('[data-accordion-section="ai-actions"]').evaluate((el) => (el as HTMLDetailsElement).open);
  // ai-actions must still be in its default state (closed) after pipeline is forced open
  expect(aiStillClosed).toBe(false);
});

// ══════════════════════════════════════════════════════════════════════════════
// PR1-T3 / PR1-T4 / PR1-T5 — Per-row probe button + badge (WILL FAIL before implementation)
// ══════════════════════════════════════════════════════════════════════════════

test("probe button renders per row for aws-postgres kind", async ({ page }) => {
  await mountSecretPanelWithProbe(page, [
    {
      handle: "grupo-topete-sit-aurora",
      kind: "aws-postgres",
      created_at: "2026-06-20T10:00:00Z",
      metadata: { secret_id: "arn:aws:secretsmanager:us-east-2:123:secret:sit", database: "sit_prod", region: "us-east-2" },
    },
  ]);

  // Probe button MUST exist for aws-postgres row
  const probeBtn = page.locator('[data-probe-handle="grupo-topete-sit-aurora"]');
  await expect(probeBtn).toHaveCount(1);
  await expect(probeBtn).toBeVisible();
  await expect(probeBtn).toContainText("Probar conexión");
});

test("probe button absent or shows not-supported for mock-postgres", async ({ page }) => {
  await mountSecretPanelWithProbe(page, [
    {
      handle: "local-mock",
      kind: "mock-postgres",
      created_at: "2026-06-20T10:00:00Z",
      metadata: { host: "localhost", port: 5432 },
    },
  ]);

  // Non-AWS kinds: button absent OR button with not-supported text
  const probeBtns = page.locator('[data-probe-handle="local-mock"]');
  const count = await probeBtns.count();
  if (count > 0) {
    // If button exists, it must show "not supported" message on click
    await probeBtns.first().click();
    const badge = page.locator('[data-probe-status="local-mock"]');
    await expect(badge).toBeVisible();
    const badgeText = await badge.textContent();
    expect(badgeText?.toLowerCase()).toMatch(/no.*soporta|not.*support/i);
  }
  // count === 0 is also acceptable (button omitted)
});

test("probe button triggers validate call and shows success badge", async ({ page }) => {
  await mountSecretPanelWithProbe(
    page,
    [
      {
        handle: "sit-aurora",
        kind: "aws-postgres",
        created_at: "2026-06-20T10:00:00Z",
        metadata: { secret_id: "arn:aws:sm:us-east-2:123:secret:sit", database: "sit_prod", region: "us-east-2" },
      },
    ],
    {
      "sit-aurora": { status: "ok", connection: "probed", message: "Conexión exitosa." },
    },
  );

  const probeBtn = page.locator('[data-probe-handle="sit-aurora"]');
  await expect(probeBtn).toBeVisible();
  await probeBtn.click();

  // Badge must appear in-place with success state
  const badge = page.locator('[data-probe-status="sit-aurora"]');
  await expect(badge).toBeVisible({ timeout: 5000 });
  await expect(badge).toContainText(/conectado|exitosa|ok/i);

  // No page reload occurred (panel DOM is still present)
  await expect(page.locator("#secret-panel")).toBeVisible();

  // Validate API was called for this handle
  const validateCalls = await page.evaluate(
    () => (window as typeof window & { __validateCalls?: string[] }).__validateCalls || [],
  );
  expect(validateCalls).toContain("sit-aurora");
});

test("probe button shows error badge on failure", async ({ page }) => {
  await mountSecretPanelWithProbe(
    page,
    [
      {
        handle: "bad-aurora",
        kind: "aws-postgres",
        created_at: "2026-06-20T10:00:00Z",
        metadata: { secret_id: "arn:aws:sm:us-east-2:123:secret:bad", database: "bad_db", region: "us-east-2" },
      },
    ],
    {
      "bad-aurora": { status: "error", connection: "probe_failed", message: "No se pudo conectar: host inalcanzable." },
    },
  );

  const probeBtn = page.locator('[data-probe-handle="bad-aurora"]');
  await expect(probeBtn).toBeVisible();
  await probeBtn.click();

  const badge = page.locator('[data-probe-status="bad-aurora"]');
  await expect(badge).toBeVisible({ timeout: 5000 });
  await expect(badge).toContainText(/error|falló|inalcanzable|no se pudo/i);
  await expect(badge).toHaveClass(/error|danger/);

  // Other rows must be unaffected (only 1 row in this test, trivially true)
  await expect(page.locator("#secret-panel")).toBeVisible();
});

test("probe badge updates in-place without page reload", async ({ page }) => {
  await mountSecretPanelWithProbe(
    page,
    [
      {
        handle: "aurora-probe",
        kind: "aws-postgres",
        created_at: "2026-06-20T10:00:00Z",
        metadata: { secret_id: "arn:aws:sm:us-east-2:123:secret:aurora", database: "prod", region: "us-east-2" },
      },
    ],
    {
      "aurora-probe": { status: "ok", connection: "probed", message: "Conectado." },
    },
  );

  // Capture a reference to the list element before click
  const listEl = page.locator(".secret-list");
  await expect(listEl).toBeVisible();

  await page.locator('[data-probe-handle="aurora-probe"]').click();

  // List element must still be there (no full re-render / page reload)
  await expect(listEl).toBeVisible();
  const badge = page.locator('[data-probe-status="aurora-probe"]');
  await expect(badge).toBeVisible({ timeout: 5000 });

  // Screenshot for visual evidence
  await page.screenshot({
    path: "test-results/pr1-typed-secrets-probe-badge.png",
    fullPage: false,
  });
});
