import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const tokensCssPath = path.resolve(__dirname, "..", "static", "tokens.css");

const APP_CSS = fs.readFileSync(tokensCssPath, "utf-8") + `
  body { margin: 0; min-height: 100vh; background: var(--bg-main); color: var(--text-normal); font-family: Inter, "Segoe UI", Arial, sans-serif; }
  main { display: grid; grid-template-columns: 320px 1fr; gap: 24px; padding: 24px; }
  .panel-card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: var(--bg-panel); }
  .panel-card-title { margin: 0; color: var(--text-muted); font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
  .search-input { min-height: 44px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: var(--bg-active); color: var(--text-normal); padding: 0 12px; }
  #search-results { margin: 0; padding: 4px; list-style: none; border: 1px solid var(--border-strong); border-radius: var(--radius-ui); background: var(--bg-panel); }
  .search-option-btn { width: 100%; min-height: 44px; text-align: left; border: 0; border-radius: var(--radius-ui); background: transparent; color: var(--text-normal); }
  .canvas-container { position: relative; min-height: 420px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: radial-gradient(circle at 40% 30%, color-mix(in srgb, var(--accent-mora) 10%, transparent), transparent 42%), var(--bg-main); }
  .d4-edge { position: absolute; height: 3px; width: 190px; top: 198px; left: 214px; background: var(--accent-mora); opacity: 1; box-shadow: 0 0 12px color-mix(in srgb, var(--accent-mora) 55%, transparent); }
  .d4-node { position: absolute; width: 26px; height: 26px; border: 0; background: transparent; color: var(--text-normal); }
  .node-circle { position: absolute; inset: 0; border-radius: 999px; border: 1px solid var(--vis-panel-border); background: var(--bg-active); }
  .node-circle::after { content: ''; position: absolute; inset: 5px; border-radius: inherit; background: var(--bg-panel-hover); }
  .node-label { position: absolute; left: 36px; top: 50%; transform: translateY(-50%); white-space: nowrap; padding: 4px 8px; border-radius: var(--radius-md); background: color-mix(in srgb, var(--bg-main) 82%, transparent); }
  .d4-node[data-hover="true"] .node-circle { border-width: 2px; border-color: var(--status-active); }
  .d4-node[data-selected="true"] .node-circle { transform: scale(1.12); border-width: 2px; border-color: var(--accent-mora); box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent-mora) 24%, transparent), 0 0 18px color-mix(in srgb, var(--accent-mora) 45%, transparent); }
  .d4-node[data-selected="true"] .node-circle::after { background: var(--accent-mora); opacity: .85; }
  .d4-node[data-search-match="true"] .node-label { background: color-mix(in srgb, var(--status-active) 18%, var(--bg-main)); color: var(--text-bright); }
`;

test("screenshot: PR2 graph search keeps selection visible during hover", async ({ page }) => {
  await page.setContent(`
    <main>
      <section class="panel-card" aria-label="Búsqueda">
        <h2 class="panel-card-title">Búsqueda</h2>
        <input id="node-search" class="search-input" value="cliente" aria-label="Búsqueda" />
        <ol id="search-results"><li><button class="search-option-btn">Cliente A (Organization) · 100.00</button></li><li><button class="search-option-btn">Ventas (Dataset) · 60.00</button></li></ol>
      </section>
      <section class="canvas-container" data-has-hover="true" data-has-selection="true" aria-label="Graph canvas">
        <span class="d4-edge" data-related="true" data-emphasis="selected"></span>
        <button class="d4-node" style="left:210px;top:210px" data-id="cliente" data-selected="true" data-hover="false" data-search-match="true" aria-selected="true"><span class="node-circle"></span><span class="node-label">Cliente A seleccionado</span></button>
        <button class="d4-node" style="left:410px;top:210px" data-id="ventas" data-selected="false" data-hover="true" data-related="true" data-search-match="true" aria-selected="false"><span class="node-circle"></span><span class="node-label">Ventas en hover</span></button>
      </section>
    </main>`, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({ content: APP_CSS });
  await expect(page.getByRole("textbox", { name: "Búsqueda" })).toBeVisible();
  await page.screenshot({ path: path.resolve(__dirname, "__screenshots__", "pr2-search-selection-hover.png"), fullPage: true });
});
