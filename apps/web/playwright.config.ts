import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4411", trace: "retain-on-failure" },
  webServer: [
    {
      command:
        "uv run --project ../../backend python ../../backend/manage.py testserver ../../fixtures/browser.json --settings=config.e2e --addrport=127.0.0.1:4412 --noinput",
      url: "http://127.0.0.1:4412/health/live",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm exec next start --hostname 127.0.0.1 --port 4411",
      url: "http://127.0.0.1:4411",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
