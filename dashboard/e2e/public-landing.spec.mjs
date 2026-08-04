import { test, expect } from "@playwright/test";

test.describe("public SaaS landing smoke", () => {
  test("home is public with Create Account and Log in", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "AI Messaging for Facebook and Instagram" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create Account" }).first()).toHaveAttribute(
      "href",
      "/register"
    );
    await expect(page.getByRole("link", { name: "Log in" }).first()).toHaveAttribute("href", "/login");
    await expect(page).not.toHaveURL(/\/login$/);
  });

  test("about and contact are public", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByRole("heading", { name: /About Linas AI/i })).toBeVisible();
    await page.goto("/contact");
    await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();
    await expect(page.getByRole("main").getByRole("link", { name: /Mahmoudalzougbhi@gmail.com/i })).toBeVisible();
  });

  test("create account and login routes open", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "Create Account" })).toBeVisible();
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /Welcome Back/i })).toBeVisible();
  });

  test("dashboard app remains protected", async ({ page }) => {
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
  });
});
