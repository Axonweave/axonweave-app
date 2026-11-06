/**
 * Settings flows against the real stack: change password, sessions, delete account.
 * These exist because unit tests mock the API and cannot catch a UI/API contract mismatch
 * (the delete-account request body was wrong until this spec's counterpart unit test was added).
 *
 * Needs the full stack (frontend, backend, Postgres, Mailpit). Creates and deletes its own user.
 * Same rate-limit notes as journey.spec.ts.
 */

import { expect, request as pwRequest, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "SettingsPass123!!";
const NEW_PASSWORD = "BrandNewPass456!!";

/** Credential check with a cookie-less client, so no session or CSRF cookie is attached. */
async function loginStatus(email: string, password: string): Promise<number> {
  const ctx = await pwRequest.newContext();
  try {
    const res = await ctx.post(`${BACKEND}/api/v1/auth/login`, {
      data: { email, password },
      headers: { "x-forwarded-for": fakeIp() },
    });
    return res.status();
  } finally {
    await ctx.dispose();
  }
}

let counter = 0;
function fakeIp(): string {
  counter += 1;
  return `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${counter}`;
}

async function withForwardedIp(page: Page, urlGlob: string) {
  await page.route(urlGlob, (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
}

async function verifyEmail(page: Page, email: string) {
  let link = "";
  await expect
    .poll(
      async () => {
        const search = await page.request.get(
          `${MAILPIT}/search?query=${encodeURIComponent(`to:${email}`)}`,
        );
        if (!search.ok()) return "";
        const { messages } = await search.json();
        if (!messages?.length) return "";
        const msg = await (await page.request.get(`${MAILPIT}/message/${messages[0].ID}`)).json();
        link =
          String(msg.Text ?? "").match(/https?:\/\/\S*verify-email\?token=[\w%.-]+/)?.[0] ?? "";
        return link;
      },
      { timeout: 20000, message: `no verification email for ${email}` },
    )
    .not.toBe("");
  await page.goto(link);
  await expect(page.getByRole("heading", { name: /email verified/i })).toBeVisible({
    timeout: 15000,
  });
}

test.describe.configure({ mode: "serial" });

test.describe("settings flows", () => {
  let page: Page;
  let email = "";

  test.beforeAll(async ({ browser }, testInfo) => {
    email = `settings-${Date.now().toString(36)}${testInfo.project.name.replace(/\W/g, "").toLowerCase()}@example.com`;
    page = await browser.newPage();
    await withForwardedIp(page, "**/api/v1/auth/register");
    await withForwardedIp(page, "**/api/v1/auth/login");
    const reg = await page.request.post(`${BACKEND}/api/v1/auth/register`, {
      data: {
        full_name: "Settings Tester",
        email,
        password: PASSWORD,
        confirm_password: PASSWORD,
        terms_accepted: true,
      },
      headers: { "x-forwarded-for": fakeIp() },
    });
    expect(reg.status()).toBe(201);
    await verifyEmail(page, email);
    await login(page, email, PASSWORD);
    await expect(page).toHaveURL(/dashboard/, { timeout: 15000 });
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("change password in the UI, then the old password stops working", async () => {
    await page.goto("/settings");
    await page.getByRole("tab", { name: "Security" }).click();
    await page.locator("#current-password").fill(PASSWORD);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByLabel("Confirm new password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText("Password changed successfully")).toBeVisible({ timeout: 10000 });

    // The API now rejects the old password and accepts the new one.
    expect(await loginStatus(email, PASSWORD)).toBe(401);
    expect(await loginStatus(email, NEW_PASSWORD)).toBe(200);
  });

  test("sessions tab lists this device as the current session", async () => {
    await page.goto("/settings");
    await page.getByRole("tab", { name: "Sessions" }).click();
    await expect(page.getByText("Current", { exact: true }).first()).toBeVisible({
      timeout: 10000,
    });
  });

  test("delete account in the UI, then the account no longer exists", async () => {
    await page.goto("/settings");
    await page.getByRole("tab", { name: "Account" }).click();
    await page.getByRole("button", { name: "Delete account" }).click();
    await page.locator("#delete-password").fill(NEW_PASSWORD);
    await page.locator("#delete-confirm").fill("delete my account");
    await page.getByRole("button", { name: "Delete my account" }).click();
    await expect(page).toHaveURL(/login|\/$/, { timeout: 15000 });

    expect(await loginStatus(email, NEW_PASSWORD)).toBe(401);
    const me = await page.request.get(`${BACKEND}/api/v1/auth/me`);
    expect(me.status()).toBe(401);
  });
});
