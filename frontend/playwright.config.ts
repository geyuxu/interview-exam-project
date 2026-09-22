import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5181",
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 960 } } },
    {
      name: "mobile",
      use: {
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: "node scripts/start-test-api.mjs",
      url: "http://127.0.0.1:8011/api/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 5181",
      url: "http://127.0.0.1:5181",
      reuseExistingServer: false,
      env: { API_PROXY_TARGET: "http://127.0.0.1:8011" },
    },
  ],
});
