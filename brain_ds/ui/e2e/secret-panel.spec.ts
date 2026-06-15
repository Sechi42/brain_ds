import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

const CANARY = "ui-secret-canary-8888";

interface SecretHandle {
  handle: string;
  kind: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

async function mountSecretPanel(
  page: import("@playwright/test").Page,
  handles: SecretHandle[],
) {
  await page.setContent('<section id="secret-panel"></section>', { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: bundlePath });
  await page.evaluate(
    async ({ handles, canary }) => {
      const schema = {
        schema_version: "1.0",
        provider_kinds: {
          postgres: { required: ["host", "port", "database", "username", "sslmode"], types: { host: "string", port: "integer", database: "string", username: "string", sslmode: "string" } },
          "google-sheets-json": { required: ["spreadsheet_id", "sheet_range", "service_account_ref"], types: { spreadsheet_id: "string", sheet_range: "string", service_account_ref: "string" } },
        },
      };

      let stored = [...handles];
      (window as typeof window & { __secretHandles?: typeof stored }).__secretHandles = stored;
      const calls: Array<{ url: string; method?: string; body?: Record<string, unknown> }> = [];
      (window as typeof window & { __secretApiCalls?: typeof calls }).__secretApiCalls = calls;

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method || "GET").toUpperCase();
        const body = init?.body ? JSON.parse(String(init.body)) : undefined;
        calls.push({ url, method, body });

        if (url.includes("/api/secrets/schema")) {
          return new Response(JSON.stringify(schema), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        if (url.includes("/api/secrets") && method === "POST") {
          stored.push({
            handle: body.handle,
            kind: body.kind,
            created_at: "2026-06-15T12:00:00Z",
            metadata: body.metadata,
          });
          return new Response(JSON.stringify({ handle: body.handle, created_at: "2026-06-15T12:00:00Z" }), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/api/secrets/") && method === "DELETE") {
          const path = url.split("?")[0] || "";
          const handle = decodeURIComponent(path.split("/").pop() || "");
          stored = stored.filter((h) => h.handle !== handle);
          return new Response(null, { status: 204 });
        }
        return new Response(JSON.stringify({ handles: stored }), { status: 200, headers: { "Content-Type": "application/json" } });
      };

      const handle = await window.brainDsUI!.secretPanel.mount(document.getElementById("secret-panel") as HTMLElement, {
        graphId: "demo-graph",
      });
      (window as typeof window & { __secretPanelHandle?: typeof handle }).__secretPanelHandle = handle;
      return handle;
    },
    { handles, canary: CANARY },
  );
}

test("panel renders handles and redacts secret-bearing metadata", async ({ page }) => {
  await mountSecretPanel(page, [
    {
      handle: "warehouse_ro",
      kind: "postgres",
      created_at: "2026-06-15T10:00:00Z",
      metadata: { host: "db.local", port: 5432, database: "warehouse", username: "etl", sslmode: "require", secret_ref: "***" },
    },
    {
      handle: "sales_q3",
      kind: "google-sheets-json",
      created_at: "2026-06-15T11:00:00Z",
      metadata: { spreadsheet_id: "abc123", sheet_range: "A1:C10", service_account_ref: "***" },
    },
  ]);

  await expect(page.locator(".secret-list")).toBeVisible();
  await expect(page.locator(".secret-handle")).toHaveCount(2);
  await expect(page.locator(".secret-handle").first()).toContainText("warehouse_ro");
  await expect(page.locator(".secret-handle").nth(1)).toContainText("sales_q3");

  const panelText = await page.locator("#secret-panel").textContent();
  expect(panelText).not.toContain(CANARY);
  expect(panelText).not.toContain("BRAINDS_WH_PWD");
  expect(panelText).not.toContain("BRAINDS_GSA");
  expect(panelText).toContain("***");
});

test("credential value input is a password field", async ({ page }) => {
  await mountSecretPanel(page, []);
  const valueInput = page.locator("#secret-new-value");
  await expect(valueInput).toHaveAttribute("type", "password");
});

test("add secret form posts to API and refreshes list without leaking value", async ({ page }) => {
  await mountSecretPanel(page, []);

  await page.locator("#secret-new-handle").fill("new_handle");
  await page.locator("#secret-new-kind").selectOption("postgres");
  await page.locator("#secret-field-host").fill("db.example.com");
  await page.locator("#secret-field-port").fill("5432");
  await page.locator("#secret-field-database").fill("db");
  await page.locator("#secret-field-username").fill("user");
  await page.locator("#secret-field-sslmode").fill("require");
  await page.locator("#secret-new-value").fill(CANARY);
  await page.locator(".secret-add-btn").click();

  await expect(page.locator(".secret-handle")).toHaveText("new_handle");

  const calls = await page.evaluate(() => (window as typeof window & { __secretApiCalls?: Array<{ body?: { raw_value?: string } }> }).__secretApiCalls || []);
  const postCall = calls.find((c) => c.body && c.body.raw_value !== undefined);
  expect(postCall?.body?.raw_value).toBe(CANARY);

  const panelText = await page.locator("#secret-panel").textContent();
  expect(panelText).not.toContain(CANARY);
});

test("remove button deletes handle after confirmation", async ({ page }) => {
  await mountSecretPanel(page, [
    { handle: "to_remove", kind: "sqlite", created_at: "2026-06-15T10:00:00Z", metadata: { path: "/tmp/db.sqlite" } },
  ]);

  page.on("dialog", (dialog) => dialog.accept());
  await page.locator(".secret-remove-btn").click();

  await expect(page.locator(".secret-handle")).toHaveCount(0);
  await expect(page.locator(".secret-panel-empty")).toBeVisible();
});

test("interactive controls have accessible labels", async ({ page }) => {
  await mountSecretPanel(page, [
    { handle: "warehouse_ro", kind: "postgres", created_at: "2026-06-15T10:00:00Z", metadata: { host: "db.local" } },
  ]);

  await expect(page.locator('label[for="secret-new-handle"]')).toHaveText("Handle");
  await expect(page.locator(".secret-remove-btn")).toHaveAttribute("aria-label", /Remove secret warehouse_ro/);
  await expect(page.locator(".secret-list")).toHaveAttribute("role", "listbox");
});

test("refresh handle re-fetches the handle list", async ({ page }) => {
  await mountSecretPanel(page, []);

  await expect(page.locator(".secret-handle")).toHaveCount(0);

  // Simulate an external change (CLI/MCP) by injecting a handle into the mock fetch store,
  // then invoke the panel's public refresh handle.
  await page.evaluate(() => {
    const stored = (window as typeof window & { __secretHandles?: unknown[] }).__secretHandles;
    if (stored) {
      stored.push({
        handle: "refreshed_pg",
        kind: "postgres",
        created_at: "2026-06-15T13:00:00Z",
        metadata: { host: "db.refreshed.local" },
      });
    }
    const handle = (window as typeof window & { __secretPanelHandle?: { refresh?: () => Promise<void> } }).__secretPanelHandle;
    return handle?.refresh?.();
  });

  await expect(page.locator(".secret-handle")).toHaveCount(1);
  await expect(page.locator(".secret-handle")).toHaveText("refreshed_pg");
});
