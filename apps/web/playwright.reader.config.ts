import { defineConfig } from "@playwright/test";
import config from "./playwright.config";

export default defineConfig({
  ...config,
  testMatch: "reader.spec.ts",
  use: { ...config.use, baseURL: "http://127.0.0.1:4413" },
  webServer: {
    command: "pnpm exec next start --hostname 127.0.0.1 --port 4413",
    url: "http://127.0.0.1:4413",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
