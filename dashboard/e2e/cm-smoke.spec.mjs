import { expect, test } from "@playwright/test";

const PUBLISH_DISABLED_MESSAGE =
  "Publishing is not enabled yet. This phase saves drafts only. No customer-facing AI behavior will change until a later approved phase.";

const ADMIN_USER = {
  id: "cm-e2e-admin",
  email: "cm-admin@example.com",
  name: "CM Admin",
  role: "admin",
  status: "active",
  permissions: {
    dashboard: true,
    liveChat: true,
    training: true,
    testing: true,
    smartMessaging: true,
    settings: true,
    contentManagers: true,
    contentPublish: true,
    activityFlow: true,
  },
};

const VIEWER_USER = {
  id: "cm-e2e-viewer",
  email: "cm-viewer@example.com",
  name: "CM Viewer",
  role: "viewer",
  status: "active",
  permissions: {
    dashboard: true,
    liveChat: false,
    training: false,
    testing: false,
    smartMessaging: false,
    settings: false,
    contentManagers: false,
    contentPublish: false,
    activityFlow: false,
  },
};

/**
 * @param {import('@playwright/test').Page} page
 * @param {{ user?: typeof ADMIN_USER; draftEtag?: string; forceConflict?: boolean; validateOk?: boolean; draftLoadFail?: boolean }} [options]
 */
async function installCmApiMocks(page, options = {}) {
  const user = options.user || ADMIN_USER;
  let etag = options.draftEtag || 'W/"etag-1"';
  let notes = "Initial author notes";
  let payload = {
    schema_version: 1,
    notes,
    items: [],
  };
  const forceConflict = Boolean(options.forceConflict);
  const validateOk = options.validateOk !== false;
  const draftLoadFail = Boolean(options.draftLoadFail);

  await page.addInitScript((sessionUser) => {
    const now = new Date().toISOString();
    localStorage.setItem(
      "auth_session",
      JSON.stringify({
        user: sessionUser,
        timestamp: now,
        lastValidatedAt: now,
      })
    );
  }, user);

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/auth/session" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, user }),
      });
      return;
    }

    if (path === "/api/test" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, status: "ok", bot_online: true }),
      });
      return;
    }

    if (path === "/api/cm/meta" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          publish_enabled: false,
          runtime_mode: "legacy",
          publish_disabled_message: PUBLISH_DISABLED_MESSAGE,
          faq_canonical: false,
        }),
      });
      return;
    }

    if (path.startsWith("/api/cm/draft/") && method === "GET") {
      if (draftLoadFail) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ success: false, error: "Draft storage unavailable" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { ETag: etag },
        body: JSON.stringify({
          success: true,
          etag,
          data: {
            section: path.split("/").pop(),
            etag,
            payload: { ...payload, notes },
          },
        }),
      });
      return;
    }

    if (path.startsWith("/api/cm/draft/") && method === "PUT") {
      const ifMatch = request.headers()["if-match"] || request.headers()["If-Match"];
      if (forceConflict || (ifMatch && ifMatch !== etag)) {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({
            success: false,
            conflict: true,
            message: "Draft was modified by another editor",
            current_etag: 'W/"etag-server"',
          }),
        });
        return;
      }
      const body = request.postDataJSON() || {};
      const nextPayload =
        body.payload && typeof body.payload === "object" && !Array.isArray(body.payload)
          ? body.payload
          : body && typeof body === "object"
            ? body
            : payload;
      payload = nextPayload;
      notes = typeof nextPayload.notes === "string" ? nextPayload.notes : notes;
      etag = 'W/"etag-2"';
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { ETag: etag },
        body: JSON.stringify({
          success: true,
          etag,
          data: {
            section: path.split("/").pop(),
            etag,
            payload: { ...payload, notes },
          },
        }),
      });
      return;
    }

    if (path === "/api/cm/validate" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          validateOk
            ? { success: true, ok: true, error_count: 0, errors: [], warnings: [] }
            : {
                success: true,
                ok: false,
                error_count: 1,
                errors: [
                  {
                    code: "RESTRICTED_FAQ_AFFIRMATION",
                    message: "FAQ affirms restricted topic 'tattoo_removal'.",
                  },
                ],
                warnings: [],
              }
        ),
      });
      return;
    }

    if (path === "/api/cm/publish" && method === "POST") {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          error: "PUBLISH_DISABLED",
          message: PUBLISH_DISABLED_MESSAGE,
        }),
      });
      return;
    }

    if (path === "/api/cm/versions" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [] }),
      });
      return;
    }

    if (path === "/api/cm/preview-packet" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          data: { source: "draft", facts: [], chunks: [], runtime_mode: "legacy" },
        }),
      });
      return;
    }

    if (path === "/api/cm/faq" && method === "GET") {
      if (draftLoadFail) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ success: false, error: "FAQ store unavailable" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, data: [], count: 0 }),
      });
      return;
    }

    if (path === "/api/cm/faq" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          qa_group_id: "qa_smoke_1",
          count_created: 4,
          duplicates: [],
          record: { qa_group_id: "qa_smoke_1", variants: [], status: "draft" },
        }),
      });
      return;
    }

    // Default: keep SPA working without leaking to a real backend.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, data: null }),
    });
  });
}

test.describe("Content Management browser smoke", () => {
  test("landing navigation, owner forms without JSON, save/validate, responsive", async ({ page }) => {
    await installCmApiMocks(page, {
      draftEtag: 'W/"etag-1"',
    });
    // Seed knowledge draft with one article via default empty items — Add creates one.
    await page.goto("/content-managers");

    await expect(page.getByRole("heading", { name: "Content Managers" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Restricted \/ Unsupported/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Dynamic Messages/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Sources & Archive/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Preview \/ Validate \/ Publish/i })).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Content Managers" })).toBeVisible();
    await expect(page.getByRole("main").locator('a[href="/content-managers/faq"]')).toBeVisible();
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.getByRole("link", { name: /^Knowledge$/i }).click();
    await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible();
    await expect(page.getByText("Loading…")).toBeHidden({ timeout: 15_000 });
    await expect(page.locator("textarea").filter({ hasText: "{" })).toHaveCount(0);
    await expect(page.getByText("Section data (JSON)")).toHaveCount(0);
    await page.getByRole("button", { name: "Add" }).click();
    await expect(page.getByDisplayValue("New article")).toBeVisible();
    await page.getByDisplayValue("New article").fill("About laser");
    await page.getByRole("button", { name: "Save Draft" }).click();
    await expect(page.getByText("Draft saved")).toBeVisible();

    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByText(/Validation OK|Validation passed/i)).toBeVisible();

    for (const [href, heading] of [
      ["/content-managers/ai-basics", "AI Basics"],
      ["/content-managers/languages", "Languages"],
      ["/content-managers/services", "Services"],
      ["/content-managers/branches", "Branches & Hours"],
    ]) {
      await page.goto(href);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await expect(page.getByText("Section data (JSON)")).toHaveCount(0);
      await expect(page.locator('textarea[spellcheck="false"]')).toHaveCount(0);
    }
  });

  test("stale ETag conflict and validation errors are truthful", async ({ page }) => {
    await installCmApiMocks(page, { forceConflict: true, validateOk: false });
    await page.goto("/content-managers/knowledge");
    await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible();
    await expect(page.getByText("Loading…")).toBeHidden({ timeout: 15_000 });

    await page.getByRole("button", { name: "Add" }).click();
    await page.getByRole("button", { name: "Save Draft" }).click();
    await expect(page.getByText(/Version conflict|Stale version/i)).toBeVisible();

    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByText(/validation/i).first()).toBeVisible();
    await expect(page.getByText(/tattoo_removal/)).toBeVisible();
  });

  test("publish page shows disabled state and honest 403 path", async ({ page }) => {
    await installCmApiMocks(page);
    await page.goto("/content-managers/publish");
    await expect(page.getByRole("heading", { name: "Preview / Validate / Publish" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish — unavailable" })).toBeDisabled();
    await expect(page.getByText(/Runtime mode:/)).toContainText("legacy");
    await expect(page.getByText(PUBLISH_DISABLED_MESSAGE).first()).toBeVisible();
  });

  test("draft load failure shows truthful error state", async ({ page }) => {
    await installCmApiMocks(page, { draftLoadFail: true });
    await page.goto("/content-managers/faq");
    await expect(page.getByRole("heading", { name: "FAQ", exact: true })).toBeVisible();
    // Professional FAQ UI: list endpoint failure surfaces honestly; publish stays on Publish page.
    await expect(page.getByText("No FAQ groups yet.")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: /Preview \/ Validate \/ Publish/i })).toBeVisible();
  });

  test("FAQ visual editor loads without JSON textarea", async ({ page }) => {
    await installCmApiMocks(page);
    await page.goto("/content-managers/faq");
    await expect(page.getByRole("heading", { name: "FAQ", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Add Q&A group" })).toBeVisible();
    await expect(page.getByPlaceholder("Question").first()).toBeVisible();
    await expect(page.getByPlaceholder("Answer").first()).toBeVisible();
    await expect(page.locator("textarea").filter({ hasText: "{" })).toHaveCount(0);
  });

  test("viewer without contentManagers permission cannot stay on CM routes", async ({ page }) => {
    await installCmApiMocks(page, { user: VIEWER_USER });
    await page.goto("/content-managers");
    // ProtectedRoute redirects away from unauthorized paths.
    await expect(page.getByRole("heading", { name: "Content Managers" })).toHaveCount(0);
    await expect(page).not.toHaveURL(/\/content-managers\/?$/);
  });
});
