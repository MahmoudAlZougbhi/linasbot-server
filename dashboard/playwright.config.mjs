import { defineConfig, devices } from "@playwright/test";

/**
 * Real Chromium browser smoke for AI Setup screens.
 * Serves a dedicated e2e Vite build (`base: "/"`) via `vite preview` and mocks CM/auth APIs.
 *
 * Browser selection:
 * - `CM_PW_EXECUTABLE`: absolute path to a Chromium/Chrome binary
 * - `CM_PW_CHANNEL=chrome|msedge|...`: Playwright browser channel
 * - `CM_PW_CHANNEL=bundled` or unset in CI: Playwright-managed Chromium from `npx playwright install`
 * - local default (no CI, no env): system Google Chrome channel
 */
function browserLaunchUse() {
  const executable = (process.env.CM_PW_EXECUTABLE || "").trim();
  if (executable) {
    return { launchOptions: { executablePath: executable } };
  }
  const channel = (process.env.CM_PW_CHANNEL || "").trim();
  if (channel && channel !== "bundled") {
    return { channel };
  }
  if (!process.env.CI && !channel) {
    return { channel: "chrome" };
  }
  return {};
}

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
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...browserLaunchUse(),
      },
    },
  ],
});
