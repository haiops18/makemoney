import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:4173", trace: "retain-on-failure" },
  webServer: process.env.E2E_BASE_URL ? undefined : { command: "npm run build && npm exec vite preview -- --host 127.0.0.1 --port 4173", port: 4173, reuseExistingServer: !process.env.CI },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
