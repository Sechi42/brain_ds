import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const tokensCssPath = path.resolve(__dirname, "..", "static", "tokens.css");

const APP_CSS = fs.readFileSync(tokensCssPath, "utf-8") + `
  body { margin: 0; min-height: 100vh; background: var(--bg-main); color: var(--text-normal); font-family: Inter, "Segoe UI", Arial, sans-serif; }
  main { display: grid; grid-template-columns: minmax(320px, .9fr) minmax(360px, 1fr); gap: 24px; padding: 24px; }
  .panel-card { display: grid; gap: 12px; padding: 16px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: var(--bg-panel); }
  .picker-section-label, .rail-section-heading { margin: 0; color: var(--text-muted); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
  .workspace-card { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: var(--bg-main); }
  .workspace-name { margin: 0; font-size: 16px; }
  .workspace-action-btn, .workspace-confirm-input { min-height: 44px; border-radius: var(--radius-ui); }
  .workspace-action-btn { border: 1px solid var(--danger-border); background: var(--danger-soft); color: var(--danger); font-weight: 700; }
  .workspace-confirm-input { border: 1px solid var(--border-subtle); background: var(--bg-panel); color: var(--text-normal); padding: 0 12px; }
  .workspace-active-ack { display: flex; align-items: center; gap: 8px; min-height: 44px; color: var(--text-muted); }
  .rail-section-group { display: flex; flex-direction: column; gap: 10px; }
  .rail-section-divider { height: 1px; border: 0; background: var(--border-subtle); margin: 12px 0; }
  .ai-actions-node-intel { display: grid; gap: 10px; }
  .ai-actions-node-intel__selected-context { display: grid; gap: 3px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); background: var(--bg-panel-hover); }
  .ai-actions-node-intel__selected-eyebrow { color: var(--text-muted); font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
  .ai-actions-node-intel__selected-id { color: var(--text-normal); }
  #ai-actions-receipts { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
  #ai-actions-receipts li { border: 1px solid var(--border-subtle); border-radius: var(--radius-ui); padding: 10px; background: var(--bg-main); }
`;

test("screenshot: PR3 workspace delete and AI Actions lifecycle states", async ({ page }) => {
  await page.setContent(`
    <main>
      <section class="panel-card" aria-label="Workspace delete">
        <p class="picker-section-label">Workspace delete</p>
        <article class="workspace-card" data-active-workspace="true">
          <h2 class="workspace-name">Revenue Ops</h2>
          <button class="workspace-action-btn" data-workspace-remove>Eliminar · Remove from list</button>
          <input class="workspace-confirm-input" value="Revenue Ops" aria-label="Type Revenue Ops or path to confirm" />
          <label class="workspace-active-ack"><input type="checkbox" checked /> I understand this is the active workspace.</label>
          <p role="status">Active workspace acknowledged before destructive delete.</p>
        </article>
      </section>
      <section class="panel-card" aria-label="AI Actions grouped rail">
        <section class="rail-section-group rail-section-group--ai-actions" aria-labelledby="ai-actions-node-heading">
          <h3 id="ai-actions-node-heading" class="rail-section-heading">Acciones IA</h3>
          <div class="ai-actions-node-intel" aria-live="polite">
            <header class="ai-actions-node-intel__selected-context">
              <span class="ai-actions-node-intel__selected-eyebrow">Nodo seleccionado</span>
              <strong class="ai-actions-node-intel__selected-id">customer-360</strong>
            </header>
            <p>Conexiones sugeridas y completitud se actualizan al abrir el panel.</p>
          </div>
        </section>
        <hr class="rail-section-divider" aria-hidden="true" />
        <section class="rail-section-group rail-section-group--pipeline" aria-labelledby="pipeline-stage-heading">
          <h3 id="pipeline-stage-heading" class="rail-section-heading">Pipeline stage</h3>
          <ol id="ai-actions-receipts"><li>intake · pending</li><li>map · ready</li></ol>
        </section>
      </section>
    </main>`, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({ content: APP_CSS });
  await expect(page.getByText("Nodo seleccionado")).toBeVisible();
  await expect(page.getByText("Pipeline stage")).toBeVisible();
  await expect(page.getByText("Eliminar")).toBeVisible();
  await page.screenshot({ path: path.resolve(__dirname, "__screenshots__", "pr3-ai-delete-lifecycle.png"), fullPage: true });
});
