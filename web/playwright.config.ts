import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "mocked-chromium", testMatch: /demo\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "mocked-mobile", testMatch: /demo\.spec\.ts/, use: { ...devices["Pixel 7"] } },
    { name: "real-backend", testMatch: /real-backend\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "CHNA_DATABASE_PATH=/tmp/chna-extractor-e2e.db CHNA_UPLOAD_DIR=/tmp/chna-extractor-e2e-uploads ../.venv/bin/uvicorn chna_extractor.api:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/healthz",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
