import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

type LiveState = {
  baseUrl: string;
  mcpBridgeUrl: string;
};

type CardSection = {
  title: string;
  content: string;
  order: number;
};

const LIVE_STATE = loadLiveState();

test.describe.configure({ mode: "serial" });

test.describe("MCP → UI live updates without reload", () => {
  test("mcp add node appears live with no reload", async ({ page, request }) => {
    const graphId = uniqueGraphId("add-node");
    await createGraph(graphId);

    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });

    const nodeId = "alpha-node";
    await callTool("update_node", {
      graph_id: graphId,
      node_id: nodeId,
      label: "Alpha node",
      type: "Role",
      card_sections: cardSections("Alpha node details"),
    });

    await expect
      .poll(async () => hasNode(request, graphId, nodeId), { timeout: 5_000 })
      .toBe(true);

    const node = page.locator(`.d4-node[data-id="${nodeId}"]`);
    const receipt = page.locator(`#ai-actions-receipts li[data-target-id="${nodeId}"]`).first();
    await expect(node).toBeVisible({ timeout: 5_000 });
    await expect(receipt).toHaveCount(1);
    await receipt.dispatchEvent("click");
    await expect(node).toHaveAttribute("data-highlight", /.+/);
  });

  test("mcp update node info reflects in detail panel live", async ({ page, request }) => {
    const graphId = uniqueGraphId("update-node-info");
    const nodeId = "beta-node";
    await createGraph(graphId);
    await callTool("update_node", {
      graph_id: graphId,
      node_id: nodeId,
      label: "Beta node",
      type: "Role",
      card_sections: cardSections("Before live update"),
    });

    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
    await page.locator(`.d4-node[data-id="${nodeId}"]`).click();
    await expect(page.locator("#detail-body")).toContainText("Before live update");

    await callTool("update_node", {
      graph_id: graphId,
      node_id: nodeId,
      label: "Beta node",
      type: "Role",
      card_sections: cardSections("After live update"),
    });

    await expect
      .poll(async () => nodeSectionText(request, graphId, nodeId), { timeout: 5_000 })
      .toContain("After live update");
    await expect(page.locator("#detail-body")).toContainText("After live update");
  });

  test("mcp delete node disappears live", async ({ page, request }) => {
    const graphId = uniqueGraphId("delete-node");
    const nodeId = "gamma-node";
    await createGraph(graphId);
    await callTool("update_node", {
      graph_id: graphId,
      node_id: nodeId,
      label: "Gamma node",
      type: "Role",
      card_sections: cardSections("Delete me"),
    });

    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
    await expect(page.locator(`.d4-node[data-id="${nodeId}"]`)).toBeVisible();

    await callTool("delete_node", { graph_id: graphId, node_id: nodeId });

    await expect
      .poll(async () => hasNode(request, graphId, nodeId), { timeout: 5_000 })
      .toBe(false);
    await expect
      .poll(
        () =>
          page.evaluate(() => {
            const api = (window as typeof window & { brainDsUI?: { network?: { data?: { nodes?: { get?: () => Array<{ id: string }> } } } } }).brainDsUI;
            return api?.network?.data?.nodes?.get?.().map((node) => node.id) ?? [];
          }),
        { timeout: 5_000 },
      )
      .not.toContain(nodeId);
    await expect(page.locator(`.d4-node[data-id="${nodeId}"]`)).toHaveCount(0);
  });

  test("mcp add edge appears live", async ({ page, request }) => {
    const graphId = uniqueGraphId("add-edge");
    await createGraph(graphId);
    await seedTwoNodes(graphId);

    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });

    await callTool("add_edge", {
      graph_id: graphId,
      source: "source-node",
      target: "target-node",
      label: "uses",
    });

    await expect
      .poll(async () => hasEdge(request, graphId, "source-node", "target-node"), { timeout: 5_000 })
      .toBe(true);
    await expect(page.locator('.d4-edge[data-source="source-node"][data-target="target-node"]')).toHaveCount(1);
  });

  test("mcp delete edge disappears live", async ({ page, request }) => {
    const graphId = uniqueGraphId("delete-edge");
    await createGraph(graphId);
    await seedTwoNodes(graphId);
    await callTool("add_edge", {
      graph_id: graphId,
      source: "source-node",
      target: "target-node",
      label: "uses",
    });

    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
    await expect(page.locator('.d4-edge[data-source="source-node"][data-target="target-node"]')).toHaveCount(1);

    await callTool("delete_edge", {
      graph_id: graphId,
      source: "source-node",
      target: "target-node",
    });

    await expect
      .poll(async () => hasEdge(request, graphId, "source-node", "target-node"), { timeout: 5_000 })
      .toBe(false);
    await expect
      .poll(
        () =>
          page.evaluate(() => {
            const api = (window as typeof window & { brainDsUI?: { network?: { data?: { edges?: { get?: () => Array<{ from?: string; to?: string; source?: string; target?: string }> } } } } }).brainDsUI;
            return (api?.network?.data?.edges?.get?.() ?? []).map((edge) => `${String(edge.from || edge.source || "")}→${String(edge.to || edge.target || "")}`);
          }),
        { timeout: 5_000 },
      )
      .not.toContain("source-node→target-node");
    await expect(page.locator('.d4-edge[data-source="source-node"][data-target="target-node"]')).toHaveCount(0);
  });

  test("live update arrives within poll budget", async ({ page }) => {
    const graphId = uniqueGraphId("poll-budget");
    await createGraph(graphId);
    await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });

    const nodeId = "budget-node";
    const startedAt = Date.now();
    await callTool("update_node", {
      graph_id: graphId,
      node_id: nodeId,
      label: "Budget node",
      type: "Role",
      card_sections: cardSections("Budget node details"),
    });

    await expect(page.locator(`.d4-node[data-id="${nodeId}"]`)).toBeVisible({ timeout: 1_000 });
    expect(Date.now() - startedAt).toBeLessThan(1_000);
  });
});

function uniqueGraphId(prefix: string): string {
  return `pw-${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function cardSections(content: string): CardSection[] {
  return [{ title: "What", content, order: 1 }];
}

async function seedTwoNodes(graphId: string): Promise<void> {
  await callTool("update_node", {
    graph_id: graphId,
    node_id: "source-node",
    label: "Source node",
    type: "Role",
    card_sections: cardSections("Source"),
  });
  await callTool("update_node", {
    graph_id: graphId,
    node_id: "target-node",
    label: "Target node",
    type: "System",
    card_sections: cardSections("Target"),
  });
}

async function createGraph(graphId: string): Promise<void> {
  await callTool("create_graph", { graph_id: graphId, name: graphId });
}

async function hasNode(request: APIRequestContext, graphId: string, nodeId: string): Promise<boolean> {
  const response = await request.get(`${LIVE_STATE.baseUrl}/api/nodes?graph_id=${encodeURIComponent(graphId)}`);
  const payload = await response.json();
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  return nodes.some((node: { id?: string }) => node.id === nodeId);
}

async function nodeSectionText(request: APIRequestContext, graphId: string, nodeId: string): Promise<string> {
  const response = await request.get(`${LIVE_STATE.baseUrl}/api/nodes?graph_id=${encodeURIComponent(graphId)}`);
  const payload = await response.json();
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const node = nodes.find((item: { id?: string }) => item.id === nodeId);
  const sections = Array.isArray(node?.card_sections) ? node.card_sections : [];
  return sections.map((section: { content?: string }) => section.content ?? "").join(" ");
}

async function hasEdge(request: APIRequestContext, graphId: string, source: string, target: string): Promise<boolean> {
  const response = await request.get(`${LIVE_STATE.baseUrl}/api/edges?graph_id=${encodeURIComponent(graphId)}`);
  const payload = await response.json();
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
  return edges.some((edge: { source?: string; target?: string }) => edge.source === source && edge.target === target);
}

async function callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const response = await fetch(`${LIVE_STATE.mcpBridgeUrl}/tool`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, arguments: args }),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`MCP tool ${name} failed: ${JSON.stringify(payload)}`);
  }
  return payload.result;
}

function loadLiveState(): LiveState {
  const baseUrl = process.env.BRAIN_DS_E2E_BASE_URL;
  const mcpBridgeUrl = process.env.BRAIN_DS_E2E_MCP_BRIDGE_URL;
  if (baseUrl && mcpBridgeUrl) {
    return { baseUrl, mcpBridgeUrl };
  }

  const stateFile = process.env.BRAIN_DS_E2E_STATE_FILE ?? path.join(os.tmpdir(), "opencode", "brain-ds-live-e2e-state.json");
  const payload = JSON.parse(readFileSync(stateFile, "utf8")) as { baseUrl?: string; mcpBridgeUrl?: string };
  if (!payload.baseUrl || !payload.mcpBridgeUrl) {
    throw new Error(`Missing required live state in ${stateFile}`);
  }
  return {
    baseUrl: payload.baseUrl,
    mcpBridgeUrl: payload.mcpBridgeUrl,
  };
}
