import { expect, test } from "@playwright/test";

const DEMO_PORT = 7777;
const BASE_URL = process.env.BRAIN_DS_ECOSYSTEM_URL ?? `http://127.0.0.1:${DEMO_PORT}`;

test.describe("Ecosystem Validation: exe → MCP → store → browser", () => {
  test("served viewer exposes workspace shell from live server", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

    await expect(page).toHaveTitle("BrainDS Graph Viewer");
    await expect(page.locator(".workspace-shell")).toBeVisible();
    await expect(page.locator('[data-rail-side="left"]')).toBeVisible();
    await expect(page.locator('[data-rail-side="right"]')).toBeVisible();
  });

  test("served viewer is backed by the live graph-store API", async ({ page }) => {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    const graphsResponse = await page.request.get(`${BASE_URL}/api/graphs`);
    expect(graphsResponse.ok()).toBeTruthy();

    const graphs = await graphsResponse.json();
    expect(Array.isArray(graphs)).toBeTruthy();
    for (const graph of graphs) {
      expect(graph).toEqual(
        expect.objectContaining({
          id: expect.any(String),
          label: expect.any(String),
        }),
      );
    }
  });

  test("served viewer API returns graph list", async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/graphs`);
    expect(response.ok()).toBeTruthy();

    const graphs = await response.json();
    expect(Array.isArray(graphs)).toBeTruthy();
  });
});
