import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("graph viewer template exposes the workspace shell", async ({ page }) => {
  const templatePath = path.resolve(__dirname, "..", "templates", "graph_viewer.html");
  const html = readFileSync(templatePath, "utf8");

  await page.setContent(html, { waitUntil: "domcontentloaded" });

  await expect(page).toHaveTitle("BrainDS Graph Viewer");
  await expect(page.locator(".workspace-shell")).toBeVisible();
  await expect(page.locator('[data-rail-side="left"]')).toBeVisible();
  await expect(page.locator('[data-rail-side="right"]')).toBeVisible();
});

test("notes blur keeps saving to the node being edited", async ({ page }) => {
  const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

  await page.setContent(`
    <div id="center-split" data-layout="collapsed"></div>
    <button id="show-more" type="button">Open</button>
    <button id="hide-markdown" type="button">Close</button>
    <div id="markdown-reader"></div>
  `);

  await page.addScriptTag({ path: bundlePath });

  await page.evaluate(() => {
    const entries = new Map([
      ["node-a", {
        id: "node-a",
        label: "Node A",
        notes: "Nota A original",
        sections: [{ title: "Resumen", content: "Contenido A" }],
        relationships: { incoming: [], outgoing: [] },
      }],
      ["node-b", {
        id: "node-b",
        label: "Node B",
        notes: "Nota B original",
        sections: [{ title: "Resumen", content: "Contenido B" }],
        relationships: { incoming: [], outgoing: [] },
      }],
    ]);

    let selectedId = "node-a";
    const saveCalls: Array<{ url: string; body: Record<string, unknown> }> = [];

    (window as typeof window & { __notesSaveCalls?: typeof saveCalls }).__notesSaveCalls = saveCalls;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = JSON.parse(String(init?.body ?? "{}"));
      saveCalls.push({ url, body });
      const nodeId = decodeURIComponent(url.split("/").pop() || "");
      const entry = entries.get(nodeId);
      if (entry) {
        entry.notes = String(((body.changes as Record<string, any>)?.details as Record<string, any>)?.notes || "");
      }
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    window.brainDsUI!.splitPane.mount(document.getElementById("center-split") as HTMLElement, {
      getMarkdown: (nodeId?: string | null) => {
        const resolved = nodeId || selectedId;
        return entries.get(resolved)?.sections?.[0]?.content || "";
      },
      saveMarkdown: async () => true,
      hasSelection: () => Boolean(selectedId),
      getSelectedNodeId: () => selectedId,
      getDetailEntry: (nodeId: string) => entries.get(nodeId) || null,
      getAllNodes: () => Array.from(entries.values()),
      selectAndReveal: (nodeId: string) => {
        selectedId = nodeId;
      },
      resolveWikilink: () => null,
      getGraphId: () => "graph-smoke",
      motionEnabled: () => false,
    });

    (window as typeof window & { __selectNodeForSmoke?: (nodeId: string | null) => void }).__selectNodeForSmoke = (nodeId) => {
      selectedId = nodeId;
    };
  });

  await page.click("#show-more");
  await page.locator(".reader-notes-view").click();
  await page.locator(".reader-notes-editor").fill("Nota A guardada");
  await page.evaluate(() => {
    (window as typeof window & { __selectNodeForSmoke?: (nodeId: string | null) => void }).__selectNodeForSmoke?.("node-b");
  });
  await page.locator("#show-more").focus();

  await expect.poll(async () => {
    return await page.evaluate(() => {
      return (window as typeof window & { __notesSaveCalls?: Array<{ url: string; body: { changes?: { details?: { notes?: string } } } }> }).__notesSaveCalls || [];
    });
  }).toHaveLength(1);

  const saveCall = await page.evaluate(() => {
    return (window as typeof window & { __notesSaveCalls?: Array<{ url: string; body: { changes?: { details?: { notes?: string } } } }> }).__notesSaveCalls?.[0] || null;
  });
  expect(saveCall?.url).toContain("/api/nodes/node-a");
  expect(saveCall?.body?.changes?.details?.notes).toBe("Nota A guardada");
  await expect(page.locator(".reader-notes-view")).toContainText("Nota A guardada");
});
