/**
 * Phase 1 journey (spec 19.4), against the real stack (frontend, backend, Postgres, Mailpit).
 *
 * register -> verify email (Mailpit) -> log in -> log out -> log in -> create workspace (UI)
 * -> subject, folder, chapter -> reload and confirm persisted -> log out -> back button
 * shows no protected data. A second user must not see any of the first user's data.
 *
 * Subject, folder and chapter are created through the REST API because their management UI is
 * not built yet (docs/DECISIONS.md and the Phase 1 closeout plan). Those steps are marked below.
 * Everything else goes through the browser.
 *
 * Registration and login are rate limited per IP (D-18). Each registration sends a unique
 * X-Forwarded-For, which the backend honours only when TRUST_PROXY_HEADERS=true (set in CI).
 * Locally without it, run the specs one project at a time to stay under the limit.
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "JourneyPass123!!";

let ipCounter = 0;
function fakeIp(): string {
  ipCounter += 1;
  return `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${ipCounter}`;
}

async function csrfHeader(page: Page): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrf_token")?.value;
  return csrf ? { "X-CSRF-Token": csrf } : {};
}

async function registerViaUi(page: Page, email: string, fullName: string) {
  await page.route("**/api/v1/auth/register", (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
  await page.goto("/register");
  await page.getByLabel(/full name/i).fill(fullName);
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByLabel(/confirm password/i).fill(PASSWORD);
  await page.getByLabel(/terms/i).check();
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible({
    timeout: 15000,
  });
}

/** Reads the verification link Axonweave emailed, via the Mailpit API. */
async function verificationLinkFor(page: Page, email: string): Promise<string> {
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
        const match = String(msg.Text ?? "").match(/https?:\/\/\S*verify-email\?token=[\w%.-]+/);
        link = match?.[0] ?? "";
        return link;
      },
      { timeout: 20000, message: `no verification email for ${email} in Mailpit` },
    )
    .not.toBe("");
  return link;
}

async function logoutViaUi(page: Page) {
  await page.getByRole("button", { name: /open profile menu/i }).click();
  await page.getByRole("menuitem", { name: /log out/i }).click();
  await expect(page).toHaveURL(/login/, { timeout: 10000 });
}

async function loginViaUi(page: Page, email: string) {
  await page.route("**/api/v1/auth/login", (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/dashboard/, { timeout: 15000 });
}

async function apiPost(page: Page, path: string, data: unknown) {
  const res = await page.request.post(`${BACKEND}/api/v1${path}`, {
    data,
    headers: await csrfHeader(page),
  });
  expect(res.status(), `POST ${path}: ${await res.text()}`).toBe(201);
  return (await res.json()).data as { id: string };
}

test.describe.configure({ mode: "serial" });

test.describe("Phase 1 journey", () => {
  let page: Page;
  let ownerEmail = "";
  let workspaceId = "";
  let subjectId = "";
  let workspaceName = "";
  const subjectName = "Organic Chemistry";
  const folderName = "Reactions";
  const chapterTitle = "Nucleophilic substitution";

  test.beforeAll(async ({ browser }, testInfo) => {
    const tag = `${Date.now().toString(36)}${testInfo.project.name.replace(/\W/g, "").toLowerCase()}`;
    ownerEmail = `journey-${tag}@example.com`;
    workspaceName = `Uni ${tag}`;
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("register shows the check-your-email confirmation", async () => {
    await registerViaUi(page, ownerEmail, "Journey Owner");
  });

  test("verify the email using the link from Mailpit", async () => {
    const link = await verificationLinkFor(page, ownerEmail);
    await page.goto(link);
    await expect(page.getByRole("heading", { name: /email verified/i })).toBeVisible({
      timeout: 15000,
    });
  });

  test("log in, log out, log in again", async () => {
    await loginViaUi(page, ownerEmail);
    await logoutViaUi(page);
    await loginViaUi(page, ownerEmail);
  });

  test("create a workspace in the UI", async () => {
    await page.goto("/workspaces");
    await page.getByRole("button", { name: /new workspace/i }).click();
    await page.getByLabel(/name/i).first().fill(workspaceName);
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByText(workspaceName)).toBeVisible({ timeout: 10000 });

    const list = await page.request.get(`${BACKEND}/api/v1/workspaces`);
    const found = (await list.json()).data.find((w: { name: string }) => w.name === workspaceName);
    expect(found).toBeTruthy();
    workspaceId = found.id;
  });

  // Subject, folder and chapter: API only, because the UI for them does not exist yet.
  test("create subject, folder and chapter (via API)", async () => {
    const subject = await apiPost(page, `/workspaces/${workspaceId}/subjects`, {
      name: subjectName,
    });
    subjectId = subject.id;
    const folder = await apiPost(page, `/workspaces/${workspaceId}/subjects/${subjectId}/folders`, {
      name: folderName,
    });
    await apiPost(page, `/workspaces/${workspaceId}/subjects/${subjectId}/chapters`, {
      title: chapterTitle,
      folder_id: folder.id,
    });
  });

  test("data persists after a reload", async () => {
    await page.goto("/workspaces");
    await page.reload();
    await expect(page.getByText(workspaceName)).toBeVisible({ timeout: 10000 });

    const base = `${BACKEND}/api/v1/workspaces/${workspaceId}/subjects/${subjectId}`;
    const subjects = await (
      await page.request.get(`${BACKEND}/api/v1/workspaces/${workspaceId}/subjects`)
    ).json();
    expect(JSON.stringify(subjects.data)).toContain(subjectName);
    expect(
      JSON.stringify((await (await page.request.get(`${base}/folders`)).json()).data),
    ).toContain(folderName);
    expect(
      JSON.stringify((await (await page.request.get(`${base}/chapters`)).json()).data),
    ).toContain(chapterTitle);
  });

  test("a second user cannot see or reach the first user's data", async ({ browser }) => {
    const ctx = await browser.newContext();
    const other = await ctx.newPage();
    const otherEmail = `other-${ownerEmail}`;
    await registerViaUi(other, otherEmail, "Other User");
    await loginViaUi(other, otherEmail);

    await other.goto("/workspaces");
    await expect(other.getByText(workspaceName)).toHaveCount(0);

    // Direct access by id is a 404, not a 403 and not data (CLAUDE.md rule 2).
    const get = await other.request.get(`${BACKEND}/api/v1/workspaces/${workspaceId}/subjects`);
    expect(get.status()).toBe(404);
    const create = await other.request.post(
      `${BACKEND}/api/v1/workspaces/${workspaceId}/subjects`,
      { data: { name: "intruder" }, headers: await csrfHeader(other) },
    );
    expect(create.status()).toBe(404);
    await ctx.close();
  });

  test("after logout the back button shows no protected data", async () => {
    await page.goto("/workspaces");
    await expect(page.getByText(workspaceName)).toBeVisible({ timeout: 10000 });
    await logoutViaUi(page);

    await page.goBack();
    await expect(page).toHaveURL(/login/, { timeout: 10000 });
    await expect(page.getByText(workspaceName)).toHaveCount(0);

    const api = await page.request.get(`${BACKEND}/api/v1/workspaces`);
    expect(api.status()).toBe(401);
  });
});

test.describe("Responsive checks", () => {
  test("login and register are usable at 375px with no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    for (const path of ["/login", "/register"]) {
      await page.goto(path);
      await expect(page.getByLabel(/email/i)).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(overflow, `${path} scrolls horizontally`).toBe(false);
    }
  });
});
