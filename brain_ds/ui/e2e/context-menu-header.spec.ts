/**
 * T1.7 — TDD Playwright tests for context-menu node mini-summary header + duplicate removal.
 *
 * Must be RED before T1.8 implementation.
 * After context-menu.ts is updated, these go GREEN.
 *
 * Covers: B5-R1/R2/R3/R4/R5/R6, CC-4, B5-S1/S2/S3/S4/S5
 */
import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

/**
 * Sets up the context menu module in isolation for testing.
 * Mounts a minimal network mock + RENDER_CONTEXT with test node data.
 */
async function mountContextMenuWithNode(
  page: import("@playwright/test").Page,
  nodeData: { id: string; label: string; type: string; score?: number; source?: string }
) {
  await page.setContent(`
    <div id="network-canvas" tabindex="0" style="width:600px;height:400px;"></div>
    <div id="test-output"></div>
  `, { waitUntil: "domcontentloaded" });

  await page.addScriptTag({ path: bundlePath });

  await page.evaluate((nd) => {
    // Build a minimal network mock that emits events
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
      nodes: [
        {
          id: nd.id,
          label: nd.label,
          type: nd.type,
          score: nd.score,
          source: nd.source,
        },
      ],
      edges: [],
    };

    const adjacency: Record<string, string[]> = {};

    // Mount the context menu module
    window.brainDsUI!.contextMenu.mount({
      network: networkMock,
      RENDER_CONTEXT,
      adjacency,
      nodes: { update: () => {} },
      edges: { update: () => {} },
      focusNode: () => {},
      resetFilters: () => {},
      toggleTheme: () => {},
    });

    // Store the emitter for tests to trigger context-menu events
    (window as any).__networkMock = networkMock;
    (window as any).__RENDER_CONTEXT = RENDER_CONTEXT;
  }, nodeData);
}

/**
 * Trigger the node context menu by emitting a context-menu event.
 */
async function openNodeContextMenu(
  page: import("@playwright/test").Page,
  nodeId: string,
  x = 200,
  y = 200
) {
  await page.evaluate(({ id, x, y }) => {
    (window as any).__networkMock.__emit("context-menu", {
      nodeId: id,
      screen: { x, y },
    });
  }, { id: nodeId, x, y });

  // Wait for menu to appear
  await page.waitForSelector("#vis-context-menu", { state: "visible" });
}

// ---------------------------------------------------------------------------
// B5-S4: menu has exactly 3 action items (not 4)
// ---------------------------------------------------------------------------

test("B5-S4: node context menu has exactly 3 action items", async ({ page }) => {
  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
    score: 0.82,
  });

  await openNodeContextMenu(page, "node-1");

  const menu = page.locator("#vis-context-menu");
  await expect(menu).toBeVisible();

  // Count actual clickable action items (button[role=menuitem]:not([disabled]))
  const actionItems = menu.locator('button[role="menuitem"]:not([disabled])');
  const count = await actionItems.count();
  expect(count).toBe(3);
});

// ---------------------------------------------------------------------------
// B5-S4: "Open detail panel" must NOT be present
// ---------------------------------------------------------------------------

test('B5-S4: "Open detail panel" item is absent from node context menu', async ({ page }) => {
  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
  });

  await openNodeContextMenu(page, "node-1");

  const menu = page.locator("#vis-context-menu");
  await expect(menu).toBeVisible();

  const menuText = await menu.textContent();
  expect(menuText).not.toContain("Open detail panel");
});

// ---------------------------------------------------------------------------
// B5-S1: non-interactive header present at top with label + type
// ---------------------------------------------------------------------------

test("B5-S1: node context menu shows non-interactive header with node label and type", async ({ page }) => {
  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
    score: 0.82,
  });

  await openNodeContextMenu(page, "node-1");

  const menu = page.locator("#vis-context-menu");
  await expect(menu).toBeVisible();

  // The header must contain the node label
  const header = menu.locator(".vis-context-menu__header");
  await expect(header).toBeVisible();

  const headerText = await header.textContent();
  expect(headerText).toContain("Cliente A");
  expect(headerText).toContain("Organization");
});

// ---------------------------------------------------------------------------
// B5-S2: header is non-interactive (no button/role=menuitem on header)
// ---------------------------------------------------------------------------

test("B5-S2: context menu header is not a clickable button (non-interactive)", async ({ page }) => {
  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
  });

  await openNodeContextMenu(page, "node-1");

  const menu = page.locator("#vis-context-menu");

  // The header must NOT be a button
  const headerAsButton = menu.locator('.vis-context-menu__header button');
  expect(await headerAsButton.count()).toBe(0);

  // The header element itself must not have role=menuitem
  const header = menu.locator(".vis-context-menu__header");
  const role = await header.getAttribute("role");
  expect(role).not.toBe("menuitem");
});

// ---------------------------------------------------------------------------
// B5-S5: remaining 3 items are functional (labels present)
// ---------------------------------------------------------------------------

test("B5-S5: remaining 3 action items are: Focus, Show neighbors, Copy JSON", async ({ page }) => {
  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
  });

  await openNodeContextMenu(page, "node-1");

  const menu = page.locator("#vis-context-menu");
  const actionItems = menu.locator('button[role="menuitem"]:not([disabled])');

  const labels = await actionItems.allTextContents();
  const combined = labels.join(" ");

  expect(combined).toContain("Focus this node");
  expect(combined).toContain("Show only this node + neighbors");
  expect(combined).toContain("Copy entity JSON to clipboard");
});

// ---------------------------------------------------------------------------
// B5-S3: no HTTP request was made to populate header
// ---------------------------------------------------------------------------

test("B5-S3: no network request is made when context menu opens (data from RENDER_CONTEXT)", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (req) => requests.push(req.url()));

  await mountContextMenuWithNode(page, {
    id: "node-1",
    label: "Cliente A",
    type: "Organization",
    score: 0.82,
  });

  const initialCount = requests.length;
  await openNodeContextMenu(page, "node-1");

  // No new requests should have been made
  expect(requests.length).toBe(initialCount);
});
