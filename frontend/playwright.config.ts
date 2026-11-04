import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  globalSetup: "./e2e/global-setup.ts",
  timeout: 60_000,
  outputDir: "test-results",
  use: { baseURL: "http://localhost:5173", screenshot: "only-on-failure" },
  projects: [
    // Screenshots are tagged @screenshots and only run via `make screenshots`.
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, grepInvert: /@screenshots/ },
    {
      name: "screenshots",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
      grep: /@screenshots/,
    },
  ],
});
