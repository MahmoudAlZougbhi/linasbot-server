import { test, expect } from "@playwright/test";

test.describe("public marketing landing smoke", () => {
  test("home is marketing-only with download CTAs and no signup CTAs", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Talk to Linas. Linas talks to your customers." })).toBeVisible();
    await expect(page.getByText("Linas AI").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Create Account" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Log in" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Ask Linas/i })).toHaveCount(0);
    await expect(page.getByRole("group", { name: "Download Linas AI" }).first()).toBeVisible();
    await expect(page.getByText("Scroll the card to explore")).toBeVisible();
    await expect(page).not.toHaveURL(/\/login$/);
  });

  test("about and contact are public", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByRole("heading", { name: /About Linas AI/i })).toBeVisible();
    await expect(page.getByRole("main")).toContainText(/Facebook/i);
    await expect(page.getByRole("main")).toContainText(/Instagram/i);
    await expect(page.getByRole("main")).toContainText(/WhatsApp/i);
    await expect(page.getByRole("main")).toContainText(/TikTok/i);
    await expect(page.getByRole("main")).toContainText(/AI Setup/i);
    await expect(page.getByRole("main")).toContainText(/Owner chat/i);
    await expect(page.getByRole("main").getByRole("link", { name: /support@linasai.com/i })).toBeVisible();
    await page.goto("/contact");
    await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: /support@linasai.com/i })).toBeVisible();
  });

  test("register redirects to marketing; ops login remains", async ({ page }) => {
    await page.goto("/register");
    await expect(page).toHaveURL(/\/#get-app|\/$/);
    await expect(page.getByRole("heading", { name: "Create Account" })).toHaveCount(0);
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /Welcome Back/i })).toBeVisible();
  });

  test("dashboard app points operators to the mobile app", async ({ page }) => {
    await page.goto("/app");
    // Locked product: /app is a public stub (not thin-auth /login, not dead operator SPA).
    await expect(page).toHaveURL(/\/app\/?$/);
    await expect(page.getByRole("heading", { name: "Use the Linas AI mobile app" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Get the app" })).toHaveAttribute("href", "/#get-app");
    await expect(page.getByText(/Operator tools/i)).toBeVisible();
  });
});
