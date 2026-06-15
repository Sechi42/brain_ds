import { expect, test } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const VENV_PYTHON = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");

const CANARY = "e2e-secret-canary-4739";
const CANARY_CLIENT_SECRET = "e2e-client-secret-canary-8847";
const CANARY_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ne2e-private-key-canary-9912\n-----END PRIVATE KEY-----";

const BASE_URL = process.env.BRAIN_DS_E2E_BASE_URL ?? "http://127.0.0.1:8765";
const MCP_BRIDGE_URL = process.env.BRAIN_DS_E2E_MCP_BRIDGE_URL ?? "http://127.0.0.1:8766";
const STATE_FILE = process.env.BRAIN_DS_E2E_STATE_FILE;

function loadSandboxRoot(): string {
  if (process.env.BRAIN_DS_E2E_SANDBOX_ROOT) {
    return process.env.BRAIN_DS_E2E_SANDBOX_ROOT;
  }
  if (STATE_FILE) {
    const state = JSON.parse(readFileSync(STATE_FILE, "utf8")) as { sandboxRoot: string };
    return state.sandboxRoot;
  }
  throw new Error("sandbox root not available; run via playwright global setup");
}

async function createGraph(request: import("@playwright/test").APIRequestContext, label: string): Promise<string> {
  const res = await request.post(`${BASE_URL}/api/graphs`, { data: { label } });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { id: string };
  return body.id;
}

async function openSecretPanel(page: import("@playwright/test").Page, graphId: string) {
  await page.goto(`${BASE_URL}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
  await expect(page.locator(".workspace-shell")).toBeVisible();
  await page.locator('[data-rail-icon="settings"]').click();
  await expect(page.locator("#secret-panel")).toBeVisible();
  await expect(page.locator("#secret-panel")).toHaveAttribute("aria-hidden", "false");
}

async function fillMockPostgresForm(
  page: import("@playwright/test").Page,
  handle: string,
  value: string,
) {
  await page.locator("#secret-new-handle").fill(handle);
  await page.locator("#secret-new-kind").selectOption("mock-postgres");
  await page.locator("#secret-field-host").fill("127.0.0.1");
  await page.locator("#secret-field-port").fill("5432");
  await page.locator("#secret-field-database").fill("warehouse");
  await page.locator("#secret-field-username").fill("etl");
  await page.locator("#secret-field-sslmode").fill("require");
  await page.locator("#secret-new-value").fill(value);
}

async function fillMockGoogleSheetsForm(
  page: import("@playwright/test").Page,
  handle: string,
  value: string,
) {
  await page.locator("#secret-new-handle").fill(handle);
  await page.locator("#secret-new-kind").selectOption("mock-google-sheets-json");
  await page.locator("#secret-field-spreadsheet_id").fill("abc123");
  await page.locator("#secret-field-sheet_range").fill("A1:C10");
  await page.locator("#secret-field-service_account_ref").fill("BRAINDS_GSA_E2E");
  await page.locator("#secret-new-value").fill(value);
}

async function addSecretViaUi(
  page: import("@playwright/test").Page,
  handle: string,
  kind: "mock-postgres" | "mock-google-sheets-json",
  value: string,
) {
  if (kind === "mock-postgres") {
    await fillMockPostgresForm(page, handle, value);
  } else {
    await fillMockGoogleSheetsForm(page, handle, value);
  }
  await page.locator(".secret-add-btn").click();
  await expect(page.locator(".secret-status--ok")).toContainText("Secret added", { timeout: 5000 });
  await expect(page.locator(".secret-handle").filter({ hasText: handle })).toBeVisible();
}

async function installLeakScans(page: import("@playwright/test").Page, canary: string) {
  const consoleMessages: string[] = [];
  page.on("console", (msg) => {
    consoleMessages.push(`${msg.type()}: ${msg.text()}`);
  });

  const responseBodies: string[] = [];
    await page.route("**/api/**", async (route) => {
      const response = await route.fetch();
      const body = await response.text().catch(() => "");
      responseBodies.push(body);
      await route.fulfill({
        status: response.status(),
        headers: response.headers(),
        body,
      });
    });

  return async () => {
    const bodyText = (await page.locator("body").textContent()) ?? "";
    return {
      dom: bodyText.includes(canary),
      console: consoleMessages.some((m) => m.includes(canary)),
      network: responseBodies.some((b) => b.includes(canary)),
    };
  };
}

function runCli(args: string[], env?: Record<string, string>, input?: string) {
  const result = spawnSync(VENV_PYTHON, ["-m", "brain_ds", ...args], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    env: { ...process.env, ...env },
    input,
  });
  return result;
}

async function callMcpTool(name: string, arguments_: Record<string, unknown>) {
  const res = await fetch(`${MCP_BRIDGE_URL}/tool`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, arguments: arguments_ }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`MCP tool ${name} failed: ${res.status} ${text}`);
  }
  const body = (await res.json()) as { result?: unknown };
  return body.result;
}

test.describe("Phase 4b: E2E anti-leak validation", () => {
  test("settings gear opens the secret panel and is keyboard reachable", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret Keyboard Test");
    await page.goto(`${BASE_URL}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });

    const gear = page.locator('[data-rail-icon="settings"]');
    await expect(gear).toBeVisible();
    await expect(gear).toHaveAttribute("aria-label", /Secret settings|configuraci.n de secretos/);

    // Activate the panel with the keyboard instead of the mouse.
    await gear.focus();
    await expect(gear).toBeFocused();
    await gear.press("Enter");
    await expect(gear).toHaveAttribute("aria-selected", "true");

    const panel = page.locator("#secret-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toHaveAttribute("aria-hidden", "false");
    await expect(panel).toHaveAttribute("aria-label", "Secret settings");

    // Shift+Tab from the gear moves focus backwards into the panel (DOM order:
    // panel shell precedes the right rail).
    await gear.press("Shift+Tab");
    const activeInPanel = await page.evaluate(() => {
      const panel = document.getElementById("secret-panel");
      const active = document.activeElement;
      return Boolean(panel && active && panel.contains(active));
    });
    expect(activeInPanel).toBe(true);
  });

  test("add mock-postgres secret via UI does not leak canary in DOM, console, or API responses", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret Postgres Leak Test");
    const scan = await installLeakScans(page, CANARY);
    await openSecretPanel(page, graphId);

    await addSecretViaUi(page, "warehouse_ro", "mock-postgres", CANARY);

    const leaks = await scan();
    expect(leaks.dom).toBe(false);
    expect(leaks.console).toBe(false);
    expect(leaks.network).toBe(false);

    // The handle and kind are visible, but the value is not.
    await expect(page.locator(".secret-handle")).toHaveText("warehouse_ro");
    const panelText = await page.locator("#secret-panel").textContent();
    expect(panelText).toContain("mock-postgres");
    expect(panelText).not.toContain(CANARY);
  });

  test("add mock-google-sheets-json secret redacts client_secret and private_key canaries", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret Google Leak Test");
    const scanClientSecret = await installLeakScans(page, CANARY_CLIENT_SECRET);
    const scanPrivateKey = await installLeakScans(page, CANARY_PRIVATE_KEY);
    await openSecretPanel(page, graphId);

    await addSecretViaUi(page, "sales_q3", "mock-google-sheets-json", `${CANARY_CLIENT_SECRET}\n${CANARY_PRIVATE_KEY}`);

    const leaksClientSecret = await scanClientSecret();
    const leaksPrivateKey = await scanPrivateKey();
    expect(leaksClientSecret.dom || leaksClientSecret.console || leaksClientSecret.network).toBe(false);
    expect(leaksPrivateKey.dom || leaksPrivateKey.console || leaksPrivateKey.network).toBe(false);

    await expect(page.locator(".secret-handle").filter({ hasText: "sales_q3" })).toBeVisible();
    const panelText = await page.locator("#secret-panel").textContent();
    expect(panelText).toContain("mock-google-sheets-json");
    expect(panelText).not.toContain(CANARY_CLIENT_SECRET);
    expect(panelText).not.toContain(CANARY_PRIVATE_KEY);
  });

  test("remove secret via UI after confirmation deletes the handle", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret Remove Test");
    await openSecretPanel(page, graphId);
    await addSecretViaUi(page, "to_remove", "mock-postgres", "remove-me-9999");

    page.on("dialog", (dialog) => dialog.accept());
    await page.locator('.secret-remove-btn[data-secret-handle="to_remove"]').click();

    await expect(page.locator(".secret-handle").filter({ hasText: "to_remove" })).toHaveCount(0);
  });

  test("MCP list_secret_handles response contains no raw canary", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret MCP List Test");
    await openSecretPanel(page, graphId);
    await addSecretViaUi(page, "mcp_canary", "mock-postgres", CANARY);

    const result = await callMcpTool("list_secret_handles", {
      agent_scope: "workspace_admin",
    });
    const resultText = JSON.stringify(result);
    expect(resultText).toContain("mcp_canary");
    expect(resultText).not.toContain(CANARY);

    const handles = (result as { handles?: Array<{ handle: string }> }).handles ?? [];
    expect(handles.some((h) => h.handle === "mcp_canary")).toBe(true);
  });

  test("MCP validate_secret_handle defaults to dry-run and explicit probe uses fixture", async ({ page, request }) => {
    const graphId = await createGraph(request, "Secret MCP Validate Test");
    await openSecretPanel(page, graphId);
    await addSecretViaUi(page, "mcp_validate", "mock-postgres", CANARY);

    const dryRun = await callMcpTool("validate_secret_handle", {
      handle: "mcp_validate",
      agent_scope: "workspace_admin",
    });
    expect(dryRun).toEqual(
      expect.objectContaining({
        valid: true,
        reason: "mcp_validate is valid (dry-run)",
      })
    );

    const probe = await callMcpTool("validate_secret_handle", {
      handle: "mcp_validate",
      agent_scope: "workspace_admin",
      probe: true,
    });
    expect(probe).toEqual(
      expect.objectContaining({
        valid: true,
        reason: "mcp_validate is valid and reachable",
      })
    );
  });

  test("CLI validate defaults to dry-run and --probe is opt-in with fixture provider", async () => {
    const sandboxRoot = loadSandboxRoot();
    const handle = `cli_canary_${Date.now()}`;

    const addRet = runCli(
      [
        "secret",
        "add",
        "--project-root",
        sandboxRoot,
        "--kind",
        "mock-postgres",
        "--handle",
        handle,
        "--metadata-json",
        JSON.stringify({
          host: "127.0.0.1",
          port: 5432,
          database: "warehouse",
          username: "etl",
          sslmode: "require",
        }),
        "--value-stdin",
      ],
      {},
      CANARY,
    );
    expect(addRet.status).toBe(0);

    const dryRun = runCli(["secret", "validate", "--project-root", sandboxRoot]);
    expect(dryRun.status).toBe(0);
    expect(dryRun.stdout).toContain("dry-run");

    const probe = runCli(["secret", "validate", "--project-root", sandboxRoot, "--probe"]);
    expect(probe.status).toBe(0);
    expect(probe.stdout).toContain("reachable");
  });
});
