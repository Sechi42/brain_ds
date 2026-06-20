/**
 * Visual evidence capture for PR1 review.
 * Saves screenshots to brain_ds/ui/e2e/baselines/ for checkpoint review.
 */
import { test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

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
  await page.setContent('<section id="secret-panel" style="max-height:400px;width:380px;border:1px solid #ccc;"></section>', {
    waitUntil: "domcontentloaded",
  });
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
  await page.setContent(`
    <div id="network-canvas" tabindex="0" style="width:600px;height:400px;background:#f5f5f5;"></div>
  `, { waitUntil: "domcontentloaded" });
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
