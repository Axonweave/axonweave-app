/**
 * Dashboard, Recent activity, Archived items and Help pages against the real stack.
 * Needs the full stack (frontend :3000, backend :8000). Creates its own user; no seeded data.
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const PASSWORD = "DashboardPass123!!";

async function registerAndLogin(page: Page) {
  const email = `dash-${Date.now().toString(36)}@example.com`;
  const reg = await page.request.post(`${BACKEND}/api/v1/auth/register`, {
    data: {
      full_name: "Dash Tester",
      email,
      password: PASSWORD,
      confirm_password: PASSWORD,
      terms_accepted: true,
    },
  });
  expect(reg.ok()).toBeTruthy();
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/dashboard/, { timeout: 10000 });
}

async function csrfHeader(page: Page): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrf_token")?.value;
  return csrf ? { "X-CSRF-Token": csrf } : {};
}

async function createArchivedWorkspace(page: Page, name: string) {
  const create = await page.request.post(`${BACKEND}/api/v1/workspaces`, {
    data: { name },
    headers: await csrfHeader(page),
  });
  expect(create.ok()).toBeTruthy();
  const ws = (await create.json()).data;
  const archive = await page.request.post(`${BACKEND}/api/v1/workspaces/${ws.id}/archive`, {
    headers: await csrfHeader(page),
  });
  expect(archive.ok(), `archive failed: ${archive.status()} ${await archive.text()}`).toBeTruthy();
}

// Registration and login are rate limited per IP (D-18), so one user and one session are
// shared by the tests below, which therefore run serially in a fixed order.
test.describe.configure({ mode: "serial" });

test.describe("dashboard pages", () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await registerAndLogin(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("new user sees real empty states, then create-workspace flows through to activity", async () => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Welcome back, Dash Tester" })).toBeVisible();
    await expect(page.getByText("No subjects yet")).toBeVisible();
    // Subject / folder / chapter quick actions must not exist until their dialogs do.
    await expect(
      page.getByRole("button", { name: /create (subject|folder|chapter)/i }),
    ).toHaveCount(0);

    await page.getByRole("button", { name: "Create workspace" }).first().click();
    await page.getByLabel(/^name/i).fill("Physics Lab");
    await page.getByRole("button", { name: "Create", exact: true }).click();

    await expect(page.getByRole("heading", { name: "Physics Lab" })).toBeVisible();
    await expect(page.getByText("Created workspace “Physics Lab”")).toBeVisible();

    await page.goto("/activity");
    await expect(page.getByText("Created workspace “Physics Lab”")).toBeVisible();
  });

  test("archive then permanently delete from Archived items", async () => {
    await createArchivedWorkspace(page, "Temp WS");
    await page.goto("/archived");
    await expect(page.getByText("Temp WS")).toBeVisible();
    await page.getByRole("button", { name: "Delete workspace Temp WS" }).click();
    await expect(page.getByText(/permanently deletes the workspace/)).toBeVisible();
    await page.getByRole("button", { name: "Delete permanently" }).click();
    await expect(page.getByText("Nothing archived")).toBeVisible();
  });

  test("restore brings an archived workspace back", async () => {
    await createArchivedWorkspace(page, "Restore Me");
    await page.goto("/archived");
    await page.getByRole("button", { name: "Restore workspace Restore Me" }).click();
    await expect(page.getByText("Nothing archived")).toBeVisible();
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Restore Me" })).toBeVisible();
  });

  test("workspaces page lists the user's workspaces", async () => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/workspaces");
    await expect(page.getByRole("heading", { name: "Workspaces", level: 1 })).toBeVisible();
    await expect(page.getByText("Personal", { exact: true })).toBeVisible();
    await expect(page.getByText("Physics Lab")).toBeVisible();
  });

  test("help page is a real static page with no fake support widgets", async () => {
    await page.goto("/help");
    await expect(page.getByRole("heading", { name: "Help & support" })).toBeVisible();
    await expect(page.getByText(/Contact support is not available yet/)).toBeVisible();
    await expect(page.getByRole("link", { name: "http://localhost:8025" })).toBeVisible();
  });

  for (const path of ["/dashboard", "/activity", "/archived", "/help"]) {
    test(`no horizontal overflow at 375px on ${path}`, async () => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
});
