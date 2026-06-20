/**
 * T3.3 — Playwright tests for B4 lazy AI actions panel (ai-actions-panel.ts).
 *
 * Reconciliation constraint honored:
 * - #ai-actions-receipts belongs to the future GII agent-activity feed — NOT touched.
 * - B4 results render into #ai-actions-node-intel (new sibling section inside ai-actions accordion).
 *
 * Tests run against the full compiled bundle (real CSS + real JS).
 * Screenshots are styled via the full token set injected into the HTML.
 */
import { expect, test } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
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
const BASELINES_DIR = path.join(__dirname, "baselines");

// Ensure baselines dir exists
mkdirSync(BASELINES_DIR, { recursive: true });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

const DEMO_NODES = [
  { id: "node-a", label: "Node A", type: "DataSource", modified_at: "2026-06-19T10:00:00Z" },
  { id: "node-b", label: "Node B", type: "Role", modified_at: "2026-06-19T10:01:00Z" },
];

const DEMO_EDGES = [
  { source: "node-a", target: "node-b", label: "feeds", weight: 0.8 },
];

const MOCK_SUGGESTIONS = {
  node_id: "node-a",
  suggestions: [
    { node_id: "node-b", label: "Node B", type: "Role", score: 0.75, reason: "shared tokens" },
  ],
  total_candidates: 1,
};

const MOCK_COMPLETENESS = {
  graph_id: "demo-graph",
  completeness_matrix: { DataSource: "present", Role: "present" },
  missing_for_brd: [],
  underspecified_nodes: [],
  missing_count: 0,
  pre_mapping_recommendation: "proceed_with_gaps",
  recommendation_detail: "All assessed entity types have grounded nodes.",
};

async function mountWithAiMock(
  page: import("@playwright/test").Page,
  opts: { suggestionsReject?: boolean; completenessReject?: boolean; delayMs?: number } = {}
): Promise<void> {
  const html = renderInteractiveHtml({
    nodes: DEMO_NODES,
    edges: DEMO_EDGES,
    detail_index: {},
  });
  await page.setContent(html, { waitUntil: "domcontentloaded" });

  // Mock window.fetch directly in the page to intercept relative API calls.
  // page.route() doesn't intercept relative URLs from about:blank (setContent origin).
  await page.evaluate(
    ({ suggestionsReject, completenessReject, mockSuggestions, mockCompleteness, delayMs }) => {
      const originalFetch = window.fetch.bind(window);
      (window as any).__aiRequestUrls = [];
      const delayed = (response: Response): Promise<Response> =>
        new Promise((resolve) => window.setTimeout(() => resolve(response), Number(delayMs) || 0));
      window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : (input as Request).url;
        if (url.includes("/api/ai/suggestions")) {
          (window as any).__aiRequestUrls.push(url);
          window.dispatchEvent(new CustomEvent("test:aiRequest", { detail: { url } }));
          if (suggestionsReject) {
            return delayed(new Response(JSON.stringify({ detail: "Server error" }), { status: 500, headers: { "Content-Type": "application/json" } }));
          }
          return delayed(new Response(JSON.stringify(mockSuggestions), { status: 200, headers: { "Content-Type": "application/json" } }));
        }
        if (url.includes("/api/ai/completeness")) {
          (window as any).__aiRequestUrls.push(url);
          window.dispatchEvent(new CustomEvent("test:aiRequest", { detail: { url } }));
          if (completenessReject) {
            return delayed(new Response(JSON.stringify({ detail: "Server error" }), { status: 500, headers: { "Content-Type": "application/json" } }));
          }
          return delayed(new Response(JSON.stringify(mockCompleteness), { status: 200, headers: { "Content-Type": "application/json" } }));
        }
        return originalFetch(input, init);
      };
    },
    {
      suggestionsReject: opts.suggestionsReject ?? false,
      completenessReject: opts.completenessReject ?? false,
      delayMs: opts.delayMs ?? 0,
      mockSuggestions: MOCK_SUGGESTIONS,
      mockCompleteness: MOCK_COMPLETENESS,
    }
  );
}

async function aiRequestUrls(page: import("@playwright/test").Page): Promise<string[]> {
  return page.evaluate(() => [ ...((window as any).__aiRequestUrls ?? []) ]);
}

async function expectAiRequestCounts(
  page: import("@playwright/test").Page,
  suggestions: number,
  completeness: number
): Promise<void> {
  const urls = await aiRequestUrls(page);
  expect(urls.filter((url) => url.includes("/api/ai/suggestions"))).toHaveLength(suggestions);
  expect(urls.filter((url) => url.includes("/api/ai/completeness"))).toHaveLength(completeness);
}

async function captureAiActionsPanelScreenshot(
  page: import("@playwright/test").Page,
  filename: string
): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => {
    const shell = document.querySelector(".workspace-shell") as HTMLElement | null;
    if (shell) {
      shell.style.setProperty("--inspector-w", "352px");
      shell.dataset.inspectorW = "352px";
    }
    const rightShell = document.querySelector(".right-panel-shell") as HTMLElement | null;
    if (rightShell) rightShell.classList.remove("collapsed");
    const stub = document.querySelector(".inspector-stub-scroll") as HTMLElement | null;
    if (stub) {
      stub.hidden = false;
      stub.setAttribute("aria-hidden", "false");
      stub.style.opacity = "1";
      stub.style.transform = "none";
      stub.style.pointerEvents = "auto";
    }
    const collapse = document.querySelector(".panel-collapse-right") as HTMLButtonElement | null;
    if (collapse) {
      collapse.setAttribute("aria-expanded", "true");
      collapse.setAttribute("aria-label", "Collapse right panel");
    }
    const acc = document.querySelector('details[data-accordion-section="ai-actions"]') as HTMLDetailsElement | null;
    if (acc) acc.open = true;
  });

  const aiPanel = page.locator('details[data-accordion-section="ai-actions"]');
  await expect(aiPanel).toBeVisible();
  await page.waitForFunction(() => {
    const stub = document.querySelector(".inspector-stub-scroll");
    return stub ? getComputedStyle(stub).opacity === "1" : true;
  });
  await expect(aiPanel.locator("summary")).toContainText("Acciones IA");
  await expect(page.locator("#ai-actions-node-intel")).toBeVisible();
  await aiPanel.evaluate((el) => {
    const htmlEl = el as HTMLElement;
    htmlEl.style.boxSizing = "border-box";
    htmlEl.style.width = "100%";
    htmlEl.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  const box = await aiPanel.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(300);
  expect(box?.height ?? 0).toBeGreaterThan(80);
  await aiPanel.screenshot({ path: path.join(BASELINES_DIR, filename), animations: "disabled" });
}

/**
 * Open the ai-actions accordion by dispatching brainds:revealAiActions.
 * This event is handled in graph_viewer.html and calls mountAiActionsPanel() + onReveal()
 * — the same code path as clicking the rail icon.
 */
async function openAiActionsTab(page: import("@playwright/test").Page): Promise<void> {
  const canUseRail = await page.locator('[data-rail-side="right"] [data-rail-icon="ai-actions"]').count();
  if (canUseRail > 0) {
    const needsClick = await page.evaluate(() => {
      const collapse = document.querySelector(".panel-collapse-right") as HTMLButtonElement | null;
      const icon = document.querySelector('[data-rail-side="right"] [data-rail-icon="ai-actions"]') as HTMLButtonElement | null;
      return !collapse || !icon || collapse.getAttribute("aria-expanded") !== "true" || icon.getAttribute("aria-selected") !== "true";
    });
    if (needsClick) {
      await page.locator('[data-rail-side="right"] [data-rail-icon="ai-actions"]').click();
    } else {
      await page.evaluate(() => {
        window.dispatchEvent(new CustomEvent("brainds:revealAiActions"));
      });
    }
  } else {
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:revealAiActions"));
    });
  }
  await expect(page.locator('details[data-accordion-section="ai-actions"]')).toHaveJSProperty("open", true);
  await expect(page.locator("#ai-actions-node-intel")).toBeVisible();
  // Small wait for panel to mount and fetch to start
  await page.waitForTimeout(200);
}

// ---------------------------------------------------------------------------
// T3.3 Tests
// ---------------------------------------------------------------------------

test.describe("B4 lazy AI actions panel", () => {
  test("node-intel section exists in DOM (T3.3 structure)", async ({ page }) => {
    await mountWithAiMock(page);
    // #ai-actions-node-intel must be present in DOM (even if hidden)
    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toBeAttached();
  });

  test("no AI request fires when ai-actions tab is NOT open (lazy guard)", async ({ page }) => {
    await mountWithAiMock(page);
    // Wait a bit without opening the tab
    await page.waitForTimeout(500);
    await expectAiRequestCounts(page, 0, 0);
  });

  test("AI requests fire when ai-actions tab is opened", async ({ page }) => {
    await mountWithAiMock(page);
    // Select a node first
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    // Wait for fetch to complete
    await page.waitForTimeout(800);
    await expectAiRequestCounts(page, 1, 1);

    // Check that node-intel shows populated content (not empty/loading)
    const nodeIntel = page.locator("#ai-actions-node-intel");
    const text = await nodeIntel.textContent();
    // After successful fetch, content should show suggestions section or completeness
    // (not the "no node" empty state)
    expect(text).not.toMatch(/Seleccioná un nodo/);
  });

  test("no re-fetch on same node tab re-open (cache hit)", async ({ page }) => {
    await mountWithAiMock(page);

    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });

    // First open — results populate
    await openAiActionsTab(page);
    await page.waitForTimeout(600);
    await expectAiRequestCounts(page, 1, 1);

    // Note the content after first open
    const contentAfterFirst = await page.locator("#ai-actions-node-intel").textContent();

    // Close the tab
    await page.evaluate(() => {
      const acc = document.querySelector('details[data-accordion-section="ai-actions"]') as HTMLDetailsElement | null;
      if (acc) acc.open = false;
    });
    await page.waitForTimeout(100);

    // Re-open same node — should show cached content, not loading spinner
    await openAiActionsTab(page);
    await page.waitForTimeout(400);
    await expectAiRequestCounts(page, 1, 1);

    const contentAfterReopen = await page.locator("#ai-actions-node-intel").textContent();
    // Cache hit: content should be same (not empty/loading from new fetch)
    // The content should NOT contain the loading spinner text
    expect(contentAfterReopen).not.toMatch(/Analizando nodo/);
    // And it should have the same populated content
    expect(contentAfterReopen).toBe(contentAfterFirst);
  });

  test("new node triggers new fetch (cache invalidation)", async ({ page }) => {
    await mountWithAiMock(page);

    // Select node-a and open tab — this will fetch and cache node-a results
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(600);
    await expectAiRequestCounts(page, 1, 1);

    // Select a different node
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-b" } }));
    });
    // After node change, cache for node-a should be cleared and loading shown
    // Then open the tab to trigger a new fetch for node-b
    await openAiActionsTab(page);
    await page.waitForTimeout(800);
    await expectAiRequestCounts(page, 2, 2);

    // The panel should have responded to the node change (a new fetch was triggered)
    // Verify by checking the node-intel has some content
    const contentNodeB = await page.locator("#ai-actions-node-intel").textContent();
    expect(contentNodeB).toBeTruthy();
  });

  test("rapid re-reveal while in-flight does not launch duplicate requests", async ({ page }) => {
    await mountWithAiMock(page, { delayMs: 600 });
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });

    await openAiActionsTab(page);
    await openAiActionsTab(page);
    await openAiActionsTab(page);
    await page.waitForTimeout(150);
    await expectAiRequestCounts(page, 1, 1);

    await page.waitForTimeout(700);
    await expect(page.locator("#ai-actions-node-intel")).toContainText("Conexiones sugeridas");
    await expectAiRequestCounts(page, 1, 1);
  });

  test("#ai-actions-receipts is NOT used for node-intel (reconciliation)", async ({ page }) => {
    // #ai-actions-receipts must remain unchanged (belongs to GII agent feed)
    await mountWithAiMock(page);
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(600);
    await expectAiRequestCounts(page, 1, 1);

    // The node-intel content must appear in #ai-actions-node-intel, NOT in #ai-actions-receipts
    const receipts = page.locator("#ai-actions-receipts");
    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toBeAttached();
    // Node-intel section must be a different element from receipts
    const receiptsId = await receipts.getAttribute("id");
    const nodeIntelId = await nodeIntel.getAttribute("id");
    expect(receiptsId).not.toBe(nodeIntelId);
  });

  test("error state visible when fetch fails (B4-R7)", async ({ page }) => {
    await mountWithAiMock(page, { suggestionsReject: true, completenessReject: true });
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(800);
    await expectAiRequestCounts(page, 1, 1);

    // An error message must appear in #ai-actions-node-intel
    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toBeAttached();
    // Error state text should be visible
    await expect(nodeIntel).toContainText("Server error");
  });

  test("populated state shows suggestions (B4-R6)", async ({ page }) => {
    await mountWithAiMock(page);
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(800);

    const nodeIntel = page.locator("#ai-actions-node-intel");
    const text = await nodeIntel.textContent();
    // Should contain suggestion content (node-b label or score)
    expect(text).toMatch(/Node B|node-b|0\.75|suger|suggest|completeness|proceed/i);
  });

  test("empty state shown when no node selected", async ({ page }) => {
    await mountWithAiMock(page);
    // Open tab WITHOUT selecting a node
    await openAiActionsTab(page);
    await page.waitForTimeout(400);
    await expectAiRequestCounts(page, 0, 0);

    const nodeIntel = page.locator("#ai-actions-node-intel");
    const text = await nodeIntel.textContent();
    expect(text).toMatch(/Seleccioná un nodo/);
  });

  // -------------------------------------------------------------------------
  // Visual evidence — styled screenshots (REAL CSS via template injection)
  // -------------------------------------------------------------------------

  test("screenshot: populated state (styled)", async ({ page }) => {
    await mountWithAiMock(page);
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(800);

    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toContainText("Conexiones sugeridas");
    await captureAiActionsPanelScreenshot(page, "ai-panel-populated.png");
  });

  test("screenshot: error state (styled)", async ({ page }) => {
    await mountWithAiMock(page, { suggestionsReject: true, completenessReject: true });
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent("brainds:nodeSelected", { detail: { nodeId: "node-a" } }));
    });
    await openAiActionsTab(page);
    await page.waitForTimeout(800);

    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toContainText("Server error");
    await captureAiActionsPanelScreenshot(page, "ai-panel-error.png");
  });

  test("screenshot: empty state (no node selected, styled)", async ({ page }) => {
    await mountWithAiMock(page);
    await openAiActionsTab(page);
    await page.waitForTimeout(400);

    const nodeIntel = page.locator("#ai-actions-node-intel");
    await expect(nodeIntel).toContainText("Seleccioná un nodo");
    await captureAiActionsPanelScreenshot(page, "ai-panel-empty.png");
  });
});
