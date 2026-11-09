import { defineConfig } from "@playwright/test";

// Runs against the app you already have running (npm run dev + the API).
// First time only:  npx playwright install chromium
// Then:             E2E_STAFF_TOKEN=<STAFF_TOKEN from backend/.env> npm run e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    viewport: { width: 1366, height: 800 },
    // Software WebGL so the maps start in headless Chromium.
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
});
