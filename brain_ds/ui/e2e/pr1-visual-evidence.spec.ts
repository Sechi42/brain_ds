/**
 * Visual evidence capture for PR1 review.
 * Saves screenshots to brain_ds/ui/e2e/baselines/ for checkpoint review.
 *
 * Injects the REAL app CSS (design tokens + vis-context-menu + secret-panel rules)
 * so screenshots reflect actual in-app styling — not bare browser defaults.
 */
import { test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");
const tokensCssPath = path.resolve(__dirname, "..", "static", "tokens.css");

// Real app CSS: tokens + vis-context-menu rules + body font + secret-panel base
const APP_CSS = (() => {
  const tokens = fs.readFileSync(tokensCssPath, "utf-8");
  const appRules = `
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, "Segoe UI", Arial, sans-serif; background: var(--bg-main); color: var(--text-normal); }

    /* === Vis context menu === */
    .vis-context-menu { min-width: 220px; padding: 0.25rem; background: var(--bg-panel); border: 1px solid var(--border-strong); border-radius: var(--radius-ui); }
    .vis-context-menu__item { width: 100%; display: flex; align-items: center; gap: 0.5rem; text-align: left; border: 0; background: transparent; padding: 0.5rem; border-radius: var(--radius-ui); color: var(--text-normal); font-family: inherit; font-size: 0.875rem; cursor: pointer; }
    .vis-context-menu__item:hover, .vis-context-menu__item--hovered { background: var(--bg-panel-hover); }
    .vis-context-menu__icon { width: 16px; height: 16px; display: inline-flex; }
    .vis-context-menu__icon svg { width: 16px; height: 16px; }
    .vis-context-menu__separator { border: 0; border-top: 1px solid var(--border-subtle); margin: 0.25rem 0; }
    .menu-item--danger { color: var(--danger); }
    /* Node mini-summary header */
    .vis-context-menu__header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.25rem 0.5rem; padding: 0.5rem 0.5rem 0.5rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: 0.25rem; pointer-events: none; user-select: none; }
    .vis-context-menu__header-label { font-weight: 600; color: var(--text-normal); font-size: 0.875rem; flex: 1 1 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .vis-context-menu__header-type { font-size: 0.75rem; color: var(--text-muted); }
    .vis-context-menu__header-score { font-size: 0.7rem; color: var(--text-muted); background: var(--bg-active); border-radius: 9999px; padding: 0.05rem 0.4rem; }
    .vis-context-menu__header-source { font-size: 0.75rem; color: var(--text-muted); }

    /* === Secret panel base === */
    #secret-panel {
      isolation: isolate;
      contain: layout;
      display: flex;
      flex-direction: column;
      height: auto;
      max-height: 400px;
      width: calc(100% - 2rem);
      max-width: 360px;
      align-self: center;
      margin: 1rem auto;
      background: var(--bg-panel);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-ui);
      overflow-y: auto;
      padding: 1rem;
      color: var(--text-normal);
      font-family: Inter, "Segoe UI", Arial, sans-serif;
      font-size: 0.875rem;
    }
    label { display: block; margin-bottom: 0.25rem; color: var(--text-muted); font-size: 0.8rem; }
    input, select { width: 100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border-strong); border-radius: var(--radius-ui); background: var(--bg-input, #18181b); color: var(--text-normal); font-size: 0.875rem; font-family: inherit; margin-bottom: 0.75rem; }
    button { font-family: inherit; cursor: pointer; }
  `;
  return tokens + "\n" + appRules;
})();

const ENRICHED_SCHEMA = {
  schema_version: "1.0",
  provider_kinds: {
    postgres: {
      required: ["host", "port", "database", "username", "sslmode", "secret_ref"],
      types: { host: "string", port: "integer", database: "string", username: "string", sslmode: "string", secret_ref: "string" },
      enums: { sslmode: ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] },
    },
    "aws-secrets": {
      required: ["region", "secret_id"],
      types: { region: "string", secret_id: "string" },
      requires_raw_value: false,
      descriptions: {
        region: "AWS region where the secret is stored, e.g. us-east-1",
        secret_id: "ARN or name of the secret in AWS Secrets Manager",
      },
      placeholders: {
        region: "us-east-1",
        secret_id: "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db/password",
      },
    },
    sqlite: {
      required: ["path"],
      types: { path: "string" },
    },
  },
};

async function mountPanel(page: import("@playwright/test").Page) {
  await page.setContent(
    '<section id="secret-panel" style="max-height:400px;width:380px;"></section>',
    { waitUntil: "domcontentloaded" }
  );
  // Inject real app CSS so screenshots show styled output
  await page.addStyleTag({ content: APP_CSS });
  await page.addScriptTag({ path: bundlePath });
  await page.evaluate(async (schema) => {
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/secrets/schema")) {
        return new Response(JSON.stringify(schema), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify({ handles: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    await window.brainDsUI!.secretPanel.mount(
      document.getElementById("secret-panel") as HTMLElement,
      { graphId: "visual-evidence" }
    );
  }, ENRICHED_SCHEMA);
}

test("screenshot: postgres sslmode renders as select dropdown", async ({ page }) => {
  await mountPanel(page);
  await page.locator("#secret-new-kind").selectOption("postgres");
  await page.waitForTimeout(200);
  await page.screenshot({
    path: path.resolve(__dirname, "baselines", "pr1-postgres-sslmode-select.png"),
    fullPage: false,
  });
});

test("screenshot: aws-secrets hides raw value field, shows hints", async ({ page }) => {
  await mountPanel(page);
  await page.locator("#secret-new-kind").selectOption("aws-secrets");
  await page.waitForTimeout(200);
  await page.screenshot({
    path: path.resolve(__dirname, "baselines", "pr1-aws-secrets-form.png"),
    fullPage: false,
  });
});

test("screenshot: context menu header with node info (3 items, no Open detail panel)", async ({ page }) => {
  await page.setContent(
    `<div id="network-canvas" tabindex="0" style="width:600px;height:400px;"></div>`,
    { waitUntil: "domcontentloaded" }
  );
  // Inject real app CSS
  await page.addStyleTag({ content: APP_CSS });
  await page.addScriptTag({ path: bundlePath });

  await page.evaluate(() => {
    const listeners: Record<string, Array<(data: unknown) => void>> = {};
    const networkMock = {
      on: (event: string, cb: (data: unknown) => void) => {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(cb);
      },
      off: () => {},
      closeContextMenu: () => {},
      canvas: document.getElementById("network-canvas"),
      __emit: (event: string, data: unknown) => {
        (listeners[event] || []).forEach(fn => fn(data));
      },
    };
    const RENDER_CONTEXT = {
      nodes: [{ id: "n1", label: "Cliente A", type: "Organization", score: 0.82, source: "CRM Export" }],
      edges: [],
    };
    window.brainDsUI!.contextMenu.mount({
      network: networkMock,
      RENDER_CONTEXT,
      adjacency: {},
      nodes: { update: () => {} },
      edges: { update: () => {} },
      focusNode: () => {},
      resetFilters: () => {},
      toggleTheme: () => {},
    });
    (window as any).__networkMock = networkMock;
  });

  await page.evaluate(() => {
    (window as any).__networkMock.__emit("context-menu", { nodeId: "n1", screen: { x: 200, y: 150 } });
  });

  await page.waitForSelector("#vis-context-menu", { state: "visible" });
  await page.waitForTimeout(200);

  await page.screenshot({
    path: path.resolve(__dirname, "baselines", "pr1-context-menu-header.png"),
    fullPage: false,
  });
});
