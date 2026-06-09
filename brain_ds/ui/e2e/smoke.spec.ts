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

  await expect(page).toHaveTitle("brain_ds Graph Viewer");
  await expect(page.locator(".workspace-shell")).toBeVisible();
  await expect(page.locator('[data-rail-side="left"]')).toBeVisible();
  await expect(page.locator('[data-rail-side="right"]')).toBeVisible();
});
