// Browser proof of the offline-first POS. Runs against the PRODUCTION export
// served by Django (the service worker only registers in a production
// build), so the target is the backend on :8000 with `out/` built — see the
// e2e job in .github/workflows/ci.yml, or locally:
//   npm run build && (cd ../backend && python manage.py seed_e2e && python manage.py runserver 8000)
//   npx playwright test
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    // The full Chromium build (new headless), not the headless shell: one
    // browser download covers headed and headless runs.
    channel: "chromium",
  },
});
