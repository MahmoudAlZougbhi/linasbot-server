import { expect, test } from "@playwright/test";

/**
 * Operator CM / AI Setup web SPA was removed (Expo owns day-to-day AI Setup).
 * Equivalent coverage lives in:
 * - mobile/linas-ai/src/features/cm/* + faqApi
 * - tests/test_cm_*.py, tests/test_sec041_faq_write_authz.py (API authz/tenant/publish)
 *
 * This suite only asserts former /content-managers bookmarks redirect to get-app.
 */
test.describe("AI Setup browser smoke", () => {
  test("former CM landing redirects to get-app", async ({ page }) => {
    await page.goto("/content-managers");
    await expect(page).toHaveURL(/\/#get-app/);
    await expect(page.getByRole("heading", { name: "AI Setup", exact: true })).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Download Linas AI" }).first()).toBeVisible();
  });

  test("former CM knowledge route redirects to get-app", async ({ page }) => {
    await page.goto("/content-managers/knowledge");
    await expect(page).toHaveURL(/\/#get-app/);
    await expect(page.getByRole("heading", { name: "Knowledge", level: 1 })).toHaveCount(0);
  });

  test("former CM publish route redirects to get-app", async ({ page }) => {
    await page.goto("/content-managers/publish");
    await expect(page).toHaveURL(/\/#get-app/);
    await expect(page.getByRole("heading", { name: "Preview / Validate / Publish" })).toHaveCount(0);
  });

  test("former CM FAQ route redirects to get-app", async ({ page }) => {
    await page.goto("/content-managers/faq");
    await expect(page).toHaveURL(/\/#get-app/);
    await expect(page.getByRole("heading", { name: /FAQ/, level: 1 })).toHaveCount(0);
  });

  test("former CM FAQ editor path is not a web SPA surface", async ({ page }) => {
    await page.goto("/content-managers/faq");
    await expect(page).toHaveURL(/\/#get-app/);
    await expect(page.getByRole("heading", { name: "Add Q&A group" })).toHaveCount(0);
    await expect(page.getByPlaceholder("Question")).toHaveCount(0);
  });

  test("viewer hitting CM routes is sent to get-app", async ({ page }) => {
    await page.goto("/content-managers");
    await expect(page.getByRole("heading", { name: "AI Setup", exact: true })).toHaveCount(0);
    await expect(page).not.toHaveURL(/\/content-managers\/?$/);
    await expect(page).toHaveURL(/\/#get-app/);
  });
});
