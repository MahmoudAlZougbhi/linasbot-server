import { defineConfig, devices } from "@playwright/test";

/**
 * Real Chromium browser smoke for Content Management screens.
 * Serves the production Vite build via `vite preview` and mocks CM/auth APIs in-page.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    // Production dashboard uses `base: "./"` for FastAPI static hosting. Deep-link browser
    // smoke needs absolute asset URLs, so build a dedicated e2e bundle with `base: "/"`.
    command:
      "npx vite build --base / --outDir build-e2e --emptyOutDir && npx vite preview --host 127.0.0.1 --port 4173 --strictPort --outDir build-e2e",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 300_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Prefer an explicit executable (local), else channel, else Playwright-managed Chromium.
        ...(process.env.CM_PW_EXECUTABLE
          ? { launchOptions: { executablePath: process.env.CM_PW_EXECUTABLE } }
          : process.env.CM_PW_CHANNEL
            ? { channel: process.env.CM_PW_CHANNEL }
            : {}),
      },
    },
  ],
});
