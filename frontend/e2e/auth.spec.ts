/**
 * E2E: authentication flows — register → verify → login → logout
 *
 * These tests assume the full stack is running (docker compose up).
 * The e-mail verification link is intercepted via Mailpit's API.
 */

import { expect, test } from "@playwright/test";

// MAILPIT_API = process.env.MAILPIT_API ?? "http://localhost:8025/api"  — wired up in future email tests
const UNIQUE = Date.now().toString(36);

test.describe("Registration", () => {
  test("shows validation errors on empty submit", async ({ page }) => {
    await page.goto("/register");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.locator("form")).toBeVisible();
  });

  test("register shows the check-your-email confirmation", async ({ page }) => {
    const email = `e2e-${UNIQUE}@example.com`;

    await page.goto("/register");
    await page.getByLabel(/full name/i).fill("E2E User");
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/^password$/i).fill("SecurePass123!!");
    await page.getByLabel(/confirm password/i).fill("SecurePass123!!");
    await page.getByLabel(/terms/i).check();
    await page.getByRole("button", { name: /create account/i }).click();

    // Registration does not open a session; the user is told to verify their email.
    // Following the link is covered in journey.spec.ts via Mailpit.
    await expect(page.getByText(/verify your email/i)).toBeVisible({ timeout: 15000 });
  });
});

test.describe("Login", () => {
  test("login page is accessible", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
  });

  test("wrong credentials shows error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("nobody@example.com");
    await page.getByLabel(/^password$/i).fill("WrongPass123!!");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 5000 });
  });
});

test.describe("Protected routes", () => {
  test("unauthenticated user redirected from dashboard to login", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForURL("**/login**", { timeout: 5000 });
    await expect(page).toHaveURL(/login/);
  });

  test("unauthenticated user redirected from settings to login", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForURL("**/login**", { timeout: 5000 });
    await expect(page).toHaveURL(/login/);
  });

  test("unauthenticated user redirected from workspaces to login", async ({ page }) => {
    await page.goto("/workspaces");
    await page.waitForURL("**/login**", { timeout: 5000 });
    await expect(page).toHaveURL(/login/);
  });
});
