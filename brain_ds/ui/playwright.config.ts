import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  reporter: "line",
  use: {
    headless: true,
  },
  outputDir: "test-results",
});
