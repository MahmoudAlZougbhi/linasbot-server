import { test, expect } from "@playwright/test";

test.describe("public marketing landing smoke", () => {
  test("home is marketing-only with guest chat and no signup CTAs", async ({ page }) => {
    await page.route("**/api/guest-ai/session", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            session: {
              id: "guest-e2e",
              questions_used: 0,
              questions_remaining: 10,
              max_questions: 10,
              max_words: 50,
              messages: [
                {
                  id: "g1",
                  role: "assistant",
                  content: "Hi — I’m Linas, your reply assistant.",
                  created_at: 1,
                },
              ],
            },
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Your business AI, in your pocket" })).toBeVisible();
    await expect(page.getByText("Linas AI").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Create Account" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Log in" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /Talk to Linas/i })).toBeVisible();
    await expect(page.getByRole("group", { name: "Download Linas AI" }).first()).toBeVisible();
    await expect(page).not.toHaveURL(/\/login$/);
  });

  test("about and contact are public", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByRole("heading", { name: /About Linas AI/i })).toBeVisible();
    await page.goto("/contact");
    await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: /Mahmoudalzougbhi@gmail.com/i })).toBeVisible();
  });

  test("register redirects to marketing; ops login remains", async ({ page }) => {
    await page.goto("/register");
    await expect(page).toHaveURL(/\/#get-app|\/$/);
    await expect(page.getByRole("heading", { name: "Create Account" })).toHaveCount(0);
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /Welcome Back/i })).toBeVisible();
  });

  test("dashboard app remains protected", async ({ page }) => {
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
  });
});
