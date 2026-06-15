import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const bundlePath = path.resolve(__dirname, "..", "assets", "viewer.bundle.js");

async function mountBrdPanel(page: import("@playwright/test").Page, markdown: string, updatedAt = "2026-02-03T10:15:00Z") {
  await page.setContent('<section id="brd-panel"></section>', { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: bundlePath });
  await page.evaluate(async ({ markdown, updatedAt }) => {
    const brdNode = {
      id: "brd-demo-graph",
      label: "BRD",
      modified_at: updatedAt,
      card_sections: [{ title: "Contenido", content: markdown, order: 0, icon: "" }],
    };
    const nodes = [
      brdNode,
      { id: "demo-role-fleet-manager", label: "Fleet Manager", modified_at: "2026-02-01T00:00:00Z" },
    ];
    const detailIndex = {
      "brd-demo-graph": {
        id: brdNode.id,
        label: brdNode.label,
        sections: brdNode.card_sections,
      },
    };
    const patchCalls: Array<{ url: string; body: Record<string, unknown> }> = [];
    (window as typeof window & { __brdPatchCalls?: typeof patchCalls }).__brdPatchCalls = patchCalls;
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if ((init?.method || "GET").toUpperCase() === "PATCH") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        patchCalls.push({ url, body });
        const changes = (body.changes ?? {}) as { card_sections?: Array<{ title: string; content: string; order: number; icon: string }> };
        brdNode.card_sections = changes.card_sections ?? brdNode.card_sections;
        detailIndex[brdNode.id].sections = brdNode.card_sections;
        return new Response(JSON.stringify({ node: { modified_at: "2026-02-04T09:00:00Z" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ nodes }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    await window.brainDsUI!.brdPanel.mount(document.getElementById("brd-panel") as HTMLElement, {
      graphId: "demo-graph",
      detailIndex,
      allNodes: nodes,
      resolveWikilink: (target: string) => (target === "Fleet Manager" ? "demo-role-fleet-manager" : null),
      selectAndReveal: (nodeId: string) => {
        (window as typeof window & { __selectedNodeId?: string }).__selectedNodeId = nodeId;
      },
    });
  }, { markdown, updatedAt });
}

test("wikilinks resolve to navigable node links", async ({ page }) => {
  await mountBrdPanel(page, "Status: COMPLETE\nOrganization: Demo Org\n\n## Executive Summary\n\nOwner: [[Fleet Manager]]");

  const wikilink = page.locator(".brd-panel-content--preview a.wikilink");
  await expect(wikilink).toHaveText("Fleet Manager");
  await expect(wikilink).toHaveAttribute("href", "#demo-role-fleet-manager");
  await expect(page.locator(".brd-panel-content--preview")).not.toContainText("[[");
});

test("freshness chip is visible in the metadata region", async ({ page }) => {
  await mountBrdPanel(page, "Status: COMPLETE\nOrganization: Demo Org\n\n## Executive Summary\n\nResumen.");

  const chip = page.locator(".brd-summary-meta .brd-freshness-chip");
  await expect(chip).toBeVisible();
  await expect(chip).toContainText("2026");
});

test("save round-trip via PATCH keeps the BRD contract", async ({ page }) => {
  await mountBrdPanel(page, "Status: COMPLETE\nOrganization: Demo Org\n\n## Executive Summary\n\nVersión inicial.");

  await page.click(".brd-edit-btn");
  await page.locator(".brd-editor").fill("Status: COMPLETE\nOrganization: Demo Org\n\n## Executive Summary\n\nVersión guardada.");
  await page.click("text=Guardar");

  await expect.poll(async () => {
    return await page.evaluate(() => {
      return (window as typeof window & { __brdPatchCalls?: Array<{ url: string; body: { changes?: { card_sections?: Array<{ title: string; order: number; icon: string; content: string }> } } }> }).__brdPatchCalls || [];
    });
  }).toHaveLength(1);

  const patchCall = await page.evaluate(() => {
    return (window as typeof window & { __brdPatchCalls?: Array<{ url: string; body: { changes?: { card_sections?: Array<{ title: string; order: number; icon: string; content: string }> } } }> }).__brdPatchCalls?.[0] || null;
  });
  expect(patchCall?.url).toContain("/api/nodes/brd-demo-graph");
  expect(patchCall?.body?.changes?.card_sections?.[0]).toEqual(
    expect.objectContaining({ title: "Contenido", order: 0, icon: "" }),
  );
  await expect(page.locator(".brd-panel-content--preview")).toContainText("Versión guardada");
});
