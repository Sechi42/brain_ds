import { expect, test, type APIRequestContext } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

type DenseFixtureNode = {
  id: string;
  x: number;
  y: number;
  degree: number;
};

type DenseFixtureEdge = {
  from: string;
  to: string;
};

type DenseFixture = {
  seed: number;
  n: number;
  focusId: string;
  neighborIds: string[];
  farIds: string[];
  drag: {
    dx: number;
    dy: number;
  };
  nodes: DenseFixtureNode[];
  edges: DenseFixtureEdge[];
};

type LiveState = {
  baseUrl: string;
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FIXTURE_PATH = path.resolve(REPO_ROOT, "tests", "fixtures", "physics_dense_natural_motion.json");
const BASELINE_DIR = path.join(__dirname, "baselines", "physics-natural-motion");
const FIXTURE = loadFixture();
const ALL_NODE_IDS = FIXTURE.nodes.map((node) => node.id);
const LIVE_STATE = loadLiveState();
const EXPECTED_BUNDLE_REVISION = "graph-physics-cold-start-pr1-20260619";

test("dense selection stays local instead of scattering unrelated nodes", async ({ page, request }) => {
  const graphId = await seedGraph(request, FIXTURE, "dense-select");

  await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
  await expect(page.locator(".d4-node")).toHaveCount(FIXTURE.nodes.length, { timeout: 15_000 });
  await assertBundleRevision(page);

  await waitForGraphToSettle(page, ALL_NODE_IDS, "pre-select settle");

  const before = await readPositions(page, FIXTURE.farIds);
  await page.screenshot({ path: path.join(BASELINE_DIR, "select-before.png"), fullPage: false });

  await clickCanvasNode(page, FIXTURE.focusId);
  await waitForGraphToSettle(page, ALL_NODE_IDS, "post-select settle");

  const after = await readPositions(page, FIXTURE.farIds);
  await page.screenshot({ path: path.join(BASELINE_DIR, "select-after.png"), fullPage: false });

  const diagonal = await graphDiagonal(page);
  const scatterThreshold = diagonal * 0.02;
  const scatter = medianDistance(before, after, FIXTURE.farIds);

  expect(scatter).toBeLessThanOrEqual(scatterThreshold);
});

test("dense drag keeps neighbors cohesive instead of pushing them away", async ({ page, request }) => {
  const graphId = await seedGraph(request, FIXTURE, "dense-drag");

  await page.goto(`${LIVE_STATE.baseUrl}/?graph_id=${encodeURIComponent(graphId)}`, { waitUntil: "networkidle" });
  await expect(page.locator(".d4-node")).toHaveCount(FIXTURE.nodes.length, { timeout: 15_000 });
  await assertBundleRevision(page);

  await waitForGraphToSettle(page, ALL_NODE_IDS, "pre-drag settle");

  const beforeNeighbors = await readPositions(page, FIXTURE.neighborIds);
  const beforeFar = await readPositions(page, FIXTURE.farIds);
  await page.screenshot({ path: path.join(BASELINE_DIR, "drag-before.png"), fullPage: false });

  const start = await canvasPointForNode(page, FIXTURE.focusId);
  await dispatchCanvasMouse(page, "mousemove", start.x, start.y, 1);
  await dispatchCanvasMouse(page, "mousedown", start.x, start.y, 1);
  for (let step = 1; step <= 16; step += 1) {
    const progress = step / 16;
    await dispatchCanvasMouse(page, "mousemove", start.x + FIXTURE.drag.dx * progress, start.y + FIXTURE.drag.dy * progress, 1);
  }
  await dispatchCanvasMouse(page, "mouseup", start.x + FIXTURE.drag.dx, start.y + FIXTURE.drag.dy, 0);
  await waitForGraphToSettle(page, ALL_NODE_IDS, "post-drag settle");

  const afterNeighbors = await readPositions(page, FIXTURE.neighborIds);
  const afterFar = await readPositions(page, FIXTURE.farIds);
  await page.screenshot({ path: path.join(BASELINE_DIR, "drag-after.png"), fullPage: false });

  const diagonal = await graphDiagonal(page);
  const dragDistance = Math.hypot(FIXTURE.drag.dx, FIXTURE.drag.dy);
  const neighborFollow = centroidAdvance(beforeNeighbors, afterNeighbors, FIXTURE.drag);
  const farScatter = medianDistance(beforeFar, afterFar, FIXTURE.farIds);

  expect(neighborFollow).toBeGreaterThanOrEqual(dragDistance * 0.25);
  expect(farScatter).toBeLessThanOrEqual(diagonal * 0.01);
});

function loadFixture(): DenseFixture {
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as DenseFixture;
}

function loadLiveState(): LiveState {
  const baseUrl = process.env.BRAIN_DS_E2E_BASE_URL;
  if (baseUrl) {
    return { baseUrl };
  }

  const stateFile = process.env.BRAIN_DS_E2E_STATE_FILE ?? path.join(os.tmpdir(), "opencode", "brain-ds-live-e2e-state.json");
  const payload = JSON.parse(readFileSync(stateFile, "utf8")) as { baseUrl?: string };
  if (!payload.baseUrl) {
    throw new Error(`Missing BRAIN_DS_E2E_BASE_URL in ${stateFile}`);
  }
  return { baseUrl: payload.baseUrl };
}

async function assertBundleRevision(page: import("@playwright/test").Page): Promise<void> {
  await expect.poll(async () => {
    return await page.evaluate(() => {
      return (window as typeof window & { brainDsUI?: { bundleRevision?: string } }).brainDsUI?.bundleRevision ?? null;
    });
  }, { timeout: 5_000 }).toBe(EXPECTED_BUNDLE_REVISION);
}

async function seedGraph(request: APIRequestContext, fixture: DenseFixture, prefix: string): Promise<string> {
  mkdirSync(BASELINE_DIR, { recursive: true });

  const label = uniqueGraphId(prefix);
  const graphResponse = await request.post(`${LIVE_STATE.baseUrl}/api/graphs`, { data: { label } });
  expect(graphResponse.ok()).toBeTruthy();
  const graphPayload = (await graphResponse.json()) as { id?: string };
  const graphId = graphPayload.id ?? label;

  await batch(fixture.nodes, 32, async (node) => {
    const response = await request.post(`${LIVE_STATE.baseUrl}/api/nodes`, {
      data: {
        graph_id: graphId,
        node: {
          id: node.id,
          label: node.id,
          type: "Role",
          details: { seed: fixture.seed, degree: node.degree },
          layout_hint: { x: node.x, y: node.y },
        },
      },
    });
    expect(response.ok()).toBeTruthy();
  });

  await batch(fixture.edges, 64, async (edge) => {
    const response = await request.post(`${LIVE_STATE.baseUrl}/api/edges`, {
      data: {
        graph_id: graphId,
        edge: {
          source: edge.from,
          target: edge.to,
          label: "depends-on",
        },
      },
    });
    expect(response.ok()).toBeTruthy();
  });

  return graphId;
}

async function clickCanvasNode(page: import("@playwright/test").Page, nodeId: string): Promise<void> {
  const point = await canvasPointForNode(page, nodeId);
  await dispatchCanvasMouse(page, "mousemove", point.x, point.y, 0);
  await dispatchCanvasMouse(page, "mousedown", point.x, point.y, 1);
  await dispatchCanvasMouse(page, "mouseup", point.x, point.y, 0);
  await dispatchCanvasMouse(page, "click", point.x, point.y, 0);
}

async function dragCanvasNode(page: import("@playwright/test").Page, nodeId: string, dx: number, dy: number): Promise<void> {
  const start = await canvasPointForNode(page, nodeId);
  await dispatchCanvasMouse(page, "mousemove", start.x, start.y, 1);
  await dispatchCanvasMouse(page, "mousedown", start.x, start.y, 1);
  for (let step = 1; step <= 16; step += 1) {
    const progress = step / 16;
    await dispatchCanvasMouse(page, "mousemove", start.x + dx * progress, start.y + dy * progress, 1);
  }
  await dispatchCanvasMouse(page, "mouseup", start.x + dx, start.y + dy, 0);
}

async function canvasPointForNode(page: import("@playwright/test").Page, nodeId: string): Promise<{ x: number; y: number }> {
  return await page.evaluate((id) => {
    const api = (window as typeof window & {
      brainDsUI?: {
        network?: {
          viewport?: { scale: number; tx: number; ty: number };
          canvas?: HTMLCanvasElement;
          data?: {
            nodes?: { get?: () => Array<{ id: string; x?: number; y?: number }> };
          };
        };
      };
    }).brainDsUI;
    const network = api?.network;
    const canvas = network?.canvas;
    const nodes = network?.data?.nodes?.get?.() ?? [];
    const node = nodes.find((item) => String(item.id) === String(id));
    if (!canvas || !node) {
      throw new Error(`Cannot resolve canvas point for ${String(id)}`);
    }
    const viewport = network?.viewport ?? { scale: 1, tx: 0, ty: 0 };
    const box = canvas.getBoundingClientRect();
    return {
      x: box.left + ((Number(node.x) || 0) * viewport.scale) + viewport.tx,
      y: box.top + ((Number(node.y) || 0) * viewport.scale) + viewport.ty,
    };
  }, nodeId);
}

async function dispatchCanvasMouse(
  page: import("@playwright/test").Page,
  type: "mousemove" | "mousedown" | "mouseup" | "click",
  x: number,
  y: number,
  buttons: number,
): Promise<void> {
  await page.evaluate(
    ({ eventType, clientX, clientY, eventButtons }) => {
      const canvas = document.querySelector<HTMLCanvasElement>(".vis-network canvas");
      if (!canvas) {
        throw new Error("Canvas not found for natural-motion interaction");
      }
      canvas.dispatchEvent(new MouseEvent(eventType, {
        bubbles: true,
        cancelable: true,
        clientX,
        clientY,
        button: 0,
        buttons: eventButtons,
        shiftKey: false,
        ctrlKey: false,
        metaKey: false,
        altKey: false,
      }));
    },
    { eventType: type, clientX: x, clientY: y, eventButtons: buttons },
  );
}

async function readPositions(page: import("@playwright/test").Page, ids: string[]): Promise<Map<string, { x: number; y: number }>> {
  const rows = await page.evaluate((nodeIds) => {
    const api = (window as typeof window & {
      brainDsUI?: {
        network?: {
          viewport?: { scale: number; tx: number; ty: number };
          data?: {
            nodes?: { get?: () => Array<{ id: string; x?: number; y?: number }> };
          };
        };
      };
    }).brainDsUI;
    const nodes = api?.network?.data?.nodes?.get?.() ?? [];
    const lookup = new Map(nodes.map((node) => [String(node.id), { x: Number(node.x) || 0, y: Number(node.y) || 0 }]));
    const viewport = api?.network?.viewport ?? { scale: 1, tx: 0, ty: 0 };
    return nodeIds.map((id) => {
      const world = lookup.get(id) ?? { x: 0, y: 0 };
      return {
        id,
        x: world.x * viewport.scale + viewport.tx,
        y: world.y * viewport.scale + viewport.ty,
      };
    });
  }, ids);

  return new Map(rows.map((row) => [row.id, { x: row.x, y: row.y }]));
}

async function graphDiagonal(page: import("@playwright/test").Page): Promise<number> {
  const box = await page.locator(".vis-network").boundingBox();
  if (box) {
    return Math.hypot(box.width, box.height);
  }

  const viewport = page.viewportSize();
  return Math.hypot(viewport?.width ?? 1280, viewport?.height ?? 720);
}

async function waitForGraphToSettle(page: import("@playwright/test").Page, ids: string[], label: string): Promise<void> {
  const stableDelta = 0.5;
  const stableSamplesRequired = 3;
  const timeoutMs = 20_000;
  const startedAt = Date.now();
  let previous = await readPositions(page, ids);
  let stableSamples = 0;

  while (Date.now() - startedAt < timeoutMs) {
    await page.waitForTimeout(250);
    const current = await readPositions(page, ids);
    const delta = maxDistance(previous, current, ids);
    const temperature = await page.evaluate(() => {
      const api = (window as typeof window & { brainDsUI?: { network?: { temperature?: number } } }).brainDsUI;
      return Number(api?.network?.temperature ?? 0);
    });
    if (delta <= stableDelta && temperature <= 0.011) {
      stableSamples += 1;
      if (stableSamples >= stableSamplesRequired) return;
    } else {
      stableSamples = 0;
    }
    previous = current;
  }

  throw new Error(`Timed out waiting for graph to settle (${label})`);
}

function medianDistance(before: Map<string, { x: number; y: number }>, after: Map<string, { x: number; y: number }>, ids: string[]): number {
  const values = ids.map((id) => distance(before.get(id), after.get(id))).sort((a, b) => a - b);
  return values[Math.floor(values.length / 2)] ?? 0;
}

function maxDistance(before: Map<string, { x: number; y: number }>, after: Map<string, { x: number; y: number }>, ids: string[]): number {
  return ids.reduce((max, id) => {
    const current = distance(before.get(id), after.get(id));
    return current > max ? current : max;
  }, 0);
}

function centroidAdvance(before: Map<string, { x: number; y: number }>, after: Map<string, { x: number; y: number }>, drag: { dx: number; dy: number }): number {
  const beforeCentroid = centroid(before);
  const afterCentroid = centroid(after);
  const deltaX = afterCentroid.x - beforeCentroid.x;
  const deltaY = afterCentroid.y - beforeCentroid.y;
  const dragDistance = Math.hypot(drag.dx, drag.dy) || 1;
  return ((deltaX * drag.dx) + (deltaY * drag.dy)) / dragDistance;
}

function centroid(points: Map<string, { x: number; y: number }>): { x: number; y: number } {
  const values = Array.from(points.values());
  if (values.length === 0) {
    return { x: 0, y: 0 };
  }
  const sum = values.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
  return { x: sum.x / values.length, y: sum.y / values.length };
}

function distance(a: { x: number; y: number } | undefined, b: { x: number; y: number } | undefined): number {
  if (!a || !b) {
    return Number.POSITIVE_INFINITY;
  }
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function uniqueGraphId(prefix: string): string {
  return `pw-${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

async function batch<T>(items: T[], size: number, fn: (item: T) => Promise<void>): Promise<void> {
  for (let index = 0; index < items.length; index += size) {
    const chunk = items.slice(index, index + size);
    await Promise.all(chunk.map((item) => fn(item)));
  }
}
