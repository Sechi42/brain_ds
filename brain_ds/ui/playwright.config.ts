import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  reporter: "line",
  workers: 1,
  use: {
    headless: true,
  },
  outputDir: "test-results",
});
