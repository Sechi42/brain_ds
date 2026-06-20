/**
 * vault-picker.spec.ts — Playwright coverage for the BrainDS vault-picker page.
 *
 * Covers:
 *   S4-A  Create workspace flow: fill #org-label-input, submit, new card appears.
 *   S4-B  Select/open flow: click [data-workspace-open], URL contains graph_id.
 *   S4-C  Remove from list (soft): card disappears, DELETE /api/graphs/{id} called.
 *   S4-D  Delete all data (hard): card gone on reload, durable.
 *
 * Infrastructure:
 *   - globalSetup spawns the UI server; baseUrl is read from BRAIN_DS_E2E_BASE_URL
 *     or the state file written by global-setup.ts.
 *   - Each test is self-contained: it creates its own graph via the API and
 *     cleans up (or relies on the action under test to clean up).
 *   - workers: 1 (see playwright.config.ts) — tests run sequentially, no shared state.
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ---------------------------------------------------------------------------
// Live state helpers (mirrors pattern from physics-natural-motion.spec.ts)
// ---------------------------------------------------------------------------

type LiveState = {
  baseUrl: string;
};

function loadLiveState(): LiveState {
  const baseUrl = process.env.BRAIN_DS_E2E_BASE_URL;
  if (baseUrl) {
    return { baseUrl };
  }
  const stateFile =
    process.env.BRAIN_DS_E2E_STATE_FILE ??
    path.join(os.tmpdir(), "opencode", "brain-ds-live-e2e-state.json");
  const payload = JSON.parse(readFileSync(stateFile, "utf8")) as { baseUrl?: string };
  if (!payload.baseUrl) {
    throw new Error(`Missing BRAIN_DS_E2E_BASE_URL in ${stateFile}`);
  }
  return { baseUrl: payload.baseUrl };
}

const LIVE_STATE = loadLiveState();

// ---------------------------------------------------------------------------
// API fixture helpers
// ---------------------------------------------------------------------------

/** Create a graph via the API and return its id. */
async function apiCreateGraph(request: APIRequestContext, label: string): Promise<string> {
  const response = await request.post(`${LIVE_STATE.baseUrl}/api/graphs`, {
    data: { label },
  });
  expect(response.ok(), `POST /api/graphs failed: ${response.status()}`).toBeTruthy();
  const payload = (await response.json()) as { id?: string };
  const id = payload.id;
  if (!id) {
    throw new Error(`POST /api/graphs returned no id: ${JSON.stringify(payload)}`);
  }
  return id;
}

/** Delete a graph via the API (hard delete for cleanup after test). */
async function apiDeleteGraph(request: APIRequestContext, graphId: string, label: string): Promise<void> {
  await request.fetch(`${LIVE_STATE.baseUrl}/api/graphs/${encodeURIComponent(graphId)}?hard=true`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    data: JSON.stringify({ typed_confirm: label }),
  });
  // Best-effort cleanup — do not assert on this.
}

/** Unique label for each test run to avoid cross-test collisions. */
function uniqueLabel(prefix: string): string {
  return `pw-${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

// ---------------------------------------------------------------------------
// Page helpers
// ---------------------------------------------------------------------------

/** Navigate to the vault-picker page and wait for it to be ready. */
async function gotoVaultPicker(page: Page): Promise<void> {
  await page.goto(`${LIVE_STATE.baseUrl}/vault-picker`, { waitUntil: "networkidle" });
}

/** Find the workspace card `<li>` element for a given graph id.
 *
 * The template renders data-graph-id on: the <li>, the <a>, the <button>, and the <form>.
 * We target the <li class="workspace-card"> specifically to avoid strict-mode ambiguity.
 */
function cardLocator(page: Page, graphId: string) {
  return page.locator(`li.workspace-card[data-graph-id="${graphId}"]`);
}

/** Open the Manage details block for a card. */
async function openManage(page: Page, graphId: string): Promise<void> {
  const card = cardLocator(page, graphId);
  const manageDetails = card.locator("details.workspace-manage");
  const manageSummary = manageDetails.locator("> summary");
  await manageSummary.click();
  // Wait until the details element carries the open attribute (boolean, no value check needed).
  await page.waitForFunction(
    (gId) => {
      const cards = document.querySelectorAll(`[data-graph-id="${gId}"]`);
      for (const el of cards) {
        const details = el.querySelector("details.workspace-manage");
        if (details instanceof HTMLDetailsElement && details.open) {
          return true;
        }
      }
      return false;
    },
    graphId,
    { timeout: 3_000 },
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/**
 * S4-A — Create workspace shows new card.
 *
 * The create form submits via JS XHR then navigates away to /?graph_id=<id>.
 * Strategy: use API to create the graph (verifying the endpoint), then reload
 * the vault-picker and assert the card appears — matching the design guidance
 * ("assert via API POST /api/graphs then reload picker").
 * This approach is robust regardless of navigation timing.
 */
test("create workspace shows new card in the list", async ({ page, request }) => {
  const label = uniqueLabel("create");

  // Create via the API (same endpoint the form calls).
  const graphId = await apiCreateGraph(request, label);

  try {
    // Navigate to vault-picker: the freshly created graph should appear.
    await gotoVaultPicker(page);

    // Assert the card is present — target the <li> card element specifically
    // (multiple elements carry data-workspace-name; scope to the card <li>).
    await expect(cardLocator(page, graphId)).toBeVisible({ timeout: 3_000 });
    // Also confirm the workspace-name heading inside the card is visible.
    await expect(cardLocator(page, graphId).locator(`[data-workspace-name="${label}"]`).first()).toBeVisible({ timeout: 3_000 });
  } finally {
    await apiDeleteGraph(request, graphId, label);
  }
});

/**
 * S4-A (UI path) — Create workspace via the UI form navigates to graph viewer.
 *
 * Tests the #create-org-form / #org-label-input flow end-to-end.
 */
test("create workspace via UI form navigates to graph viewer", async ({ page, request }) => {
  const label = uniqueLabel("ui-create");
  let createdId: string | null = null;

  // Intercept the POST /api/graphs response to capture the created id for cleanup.
  await page.route("**/api/graphs", async (route) => {
    const response = await route.fetch();
    const body = await response.json() as { id?: string };
    if (body.id) {
      createdId = body.id;
    }
    await route.fulfill({ response });
  });

  await gotoVaultPicker(page);

  // Fill the form and submit.
  await page.fill("#org-label-input", label);
  await page.click("#create-org-form button[type='submit']");

  // After success the JS navigates to /?graph_id=<id>.
  await page.waitForURL((url) => url.searchParams.has("graph_id"), { timeout: 5_000 });
  expect(page.url()).toContain("graph_id=");

  // Cleanup.
  if (createdId) {
    await apiDeleteGraph(request, createdId, label);
  }
});

/**
 * S4-B — Select/open navigates to graph viewer.
 *
 * Clicking [data-workspace-open] on a card should navigate to /?graph_id=<id>.
 */
test("select/open workspace navigates to graph viewer URL", async ({ page, request }) => {
  const label = uniqueLabel("select");
  const graphId = await apiCreateGraph(request, label);

  try {
    await gotoVaultPicker(page);

    // Wait for the card to be visible.
    await expect(cardLocator(page, graphId)).toBeVisible({ timeout: 3_000 });

    // Click the primary "Open workspace" CTA.
    const openCta = cardLocator(page, graphId).locator("[data-workspace-open]");
    await openCta.click();

    // Assert navigation to the graph viewer URL.
    await page.waitForURL((url) => url.searchParams.get("graph_id") === graphId, { timeout: 5_000 });
    expect(page.url()).toContain(`graph_id=${graphId}`);
  } finally {
    // Graph may have been navigated to; hard-delete via API.
    await apiDeleteGraph(request, graphId, label);
  }
});

/**
 * S4-C — Remove from list removes card and calls /api/graphs/{id} (not /api/workspaces/…).
 *
 * Network assertion: the DELETE URL must match /api/graphs/<uuid>, not /api/workspaces/.
 */
test("remove from list removes card and calls correct endpoint", async ({ page, request }) => {
  const label = uniqueLabel("remove");
  const graphId = await apiCreateGraph(request, label);
  const activeLabel = uniqueLabel("active");
  const activeGraphId = await apiCreateGraph(request, activeLabel);

  // Track DELETE requests to verify endpoint correctness.
  const deleteRequests: string[] = [];
  page.on("request", (req) => {
    if (req.method() === "DELETE") {
      deleteRequests.push(req.url());
    }
  });

  await gotoVaultPicker(page);

  // Card must be present before attempting removal.
  await expect(cardLocator(page, graphId)).toBeVisible({ timeout: 3_000 });

  // Open the Manage block.
  await openManage(page, graphId);

  // Click "Remove from list".
  const removeBtn = cardLocator(page, graphId).locator("[data-workspace-remove]");
  await expect(removeBtn).toBeVisible({ timeout: 2_000 });

  // Wait for the DELETE response to complete after clicking.
  const [deleteResponse] = await Promise.all([
    page.waitForResponse(
      (resp) => resp.url().includes(`/api/graphs/${graphId}`) && resp.request().method() === "DELETE",
      { timeout: 5_000 },
    ),
    removeBtn.click(),
  ]);

  // Verify response was successful.
  expect(deleteResponse.ok()).toBeTruthy();

  // Card must disappear from the DOM.
  await expect(cardLocator(page, graphId)).not.toBeVisible({ timeout: 3_000 });

  // Network assertion: DELETE hit /api/graphs/<id>, NOT /api/workspaces/.
  const deletedUrls = deleteRequests.filter((url) => url.includes(`/api/graphs/${graphId}`));
  expect(deletedUrls.length).toBeGreaterThan(0);
  const workspacesHit = deleteRequests.filter((url) => url.includes("/api/workspaces/"));
  expect(workspacesHit.length).toBe(0);

  // Graph is soft-hidden — no cleanup needed (already removed from list).
  await apiDeleteGraph(request, activeGraphId, activeLabel);
});

/**
 * S4-D — Delete all data removes card permanently (durable across reload).
 *
 * Opens Manage → danger zone, fills typed_confirm, submits, and verifies:
 * 1. Card disappears from DOM.
 * 2. Reloading /vault-picker still shows no card for that graph_id.
 */
test("delete all data removes card permanently across reload", async ({ page, request }) => {
  const label = uniqueLabel("delete");
  const graphId = await apiCreateGraph(request, label);

  await gotoVaultPicker(page);

  // Card must be present.
  await expect(cardLocator(page, graphId)).toBeVisible({ timeout: 3_000 });

  // Open Manage block.
  await openManage(page, graphId);

  // Open the danger zone (nested <details class="workspace-danger-zone">).
  const dangerZone = cardLocator(page, graphId).locator("details.workspace-danger-zone");
  await dangerZone.locator("summary").click();

  // Fill the typed_confirm input with the workspace label (matches backend logic).
  const confirmInput = cardLocator(page, graphId).locator("input[name='typed_confirm']");
  await expect(confirmInput).toBeVisible({ timeout: 2_000 });
  await confirmInput.fill(label);

  const activeAck = cardLocator(page, graphId).locator("input[name='active_acknowledged']");
  if (await activeAck.isVisible()) {
    await activeAck.check();
  }

  // Submit button should be enabled once confirmation matches.
  const submitBtn = cardLocator(page, graphId).locator(".workspace-danger-form button[type='submit']");
  await expect(submitBtn).not.toBeDisabled({ timeout: 2_000 });

  // Track the DELETE /api/graphs/{id}?hard=true response.
  const [deleteResponse] = await Promise.all([
    page.waitForResponse(
      (resp) =>
        resp.url().includes(`/api/graphs/${graphId}`) &&
        resp.url().includes("hard=true") &&
        resp.request().method() === "DELETE",
      { timeout: 5_000 },
    ),
    submitBtn.click(),
  ]);

  expect(deleteResponse.ok()).toBeTruthy();

  // Card must disappear from DOM.
  await expect(cardLocator(page, graphId)).not.toBeVisible({ timeout: 3_000 });

  // Durability check: reload /vault-picker and confirm graph is still gone.
  await gotoVaultPicker(page);
  await expect(cardLocator(page, graphId)).not.toBeVisible({ timeout: 3_000 });
  await expect(page.locator(`[data-workspace-name="${label}"]`)).not.toBeVisible({ timeout: 2_000 });
});
