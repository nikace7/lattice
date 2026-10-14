import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: ["ui.spec.ts", "reader.spec.ts", "security.spec.ts"],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4411", trace: "retain-on-failure" },
  webServer: {
    command: "pnpm exec next start --hostname 127.0.0.1 --port 4411",
    url: "http://127.0.0.1:4411",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
