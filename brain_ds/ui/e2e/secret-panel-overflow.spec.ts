/**
 * T1.6 — TDD Playwright test for #secret-panel overflow fix.
 *
 * Must be RED before graph_viewer.html is updated.
 * After overflow-y:auto fix it goes GREEN.
 *
 * Covers: A3-R1/R2, A3-S1
 */
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

test("A3-S1: #secret-panel has overflow-y:auto so it is scrollable, not clipped", async ({ page }) => {
  // Mount the panel in a constrained-height container to simulate Tauri window sizing
  await page.setContent(`
    <style>
      body { margin: 0; padding: 0; }
      .right-shell { height: 300px; overflow: hidden; display: flex; flex-direction: column; }
    </style>
    <div class="right-shell">
      <section id="secret-panel" style="flex:1;"></section>
    </div>
  `, { waitUntil: "domcontentloaded" });

  // Inject the #secret-panel CSS from the template
  const templatePath = path.resolve(__dirname, "..", "templates", "graph_viewer.html");
  const html = readFileSync(templatePath, "utf8");

  // Extract the #secret-panel CSS rule from the template
  const cssMatch = html.match(/#secret-panel\s*\{[^}]+\}/);
  if (cssMatch) {
    await page.addStyleTag({ content: cssMatch[0] });
  }

  // Check the computed overflow-y on #secret-panel
  const overflowY = await page.locator("#secret-panel").evaluate((el) => {
    return window.getComputedStyle(el).overflowY;
  });

  // Must be 'auto' (or 'scroll') — NOT 'hidden' or 'visible'
  expect(["auto", "scroll"]).toContain(overflowY);
});

test("A3-R1: #secret-panel CSS in graph_viewer.html must not set overflow:hidden without overflow-y:auto", async ({ page }) => {
  const templatePath = path.resolve(__dirname, "..", "templates", "graph_viewer.html");
  const html = readFileSync(templatePath, "utf8");

  // Find the #secret-panel CSS block
  const cssMatch = html.match(/#secret-panel\s*\{[^}]+\}/s);
  expect(cssMatch).not.toBeNull();
  const cssBlock = cssMatch![0];

  // Must have overflow-y: auto
  expect(cssBlock).toMatch(/overflow-y\s*:\s*auto/);

  // Must NOT have overflow: hidden that would clip the panel
  // (overflow: hidden at the top level blocks scrolling)
  // Allow "overflow: hidden" if followed by explicit overflow-y: auto
  if (/overflow\s*:\s*hidden/.test(cssBlock)) {
    // If overflow:hidden is present, overflow-y:auto MUST also be present to override it
    expect(cssBlock).toMatch(/overflow-y\s*:\s*auto/);
  }
});
