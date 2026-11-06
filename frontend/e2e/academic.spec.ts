/**
 * Subjects, folders and chapters through the browser, against the real stack.
 *
 * Only account setup (register, verify via Mailpit, log in) and creating the workspace use helpers;
 * every subject / folder / chapter action below is done in the UI. The API is used to read state
 * back, to prove the UI changed the database and not just the screen.
 *
 * Needs TRUST_PROXY_HEADERS=true on the backend for the per-request X-Forwarded-For (see
 * journey.spec.ts); CI sets it.
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "AcademicPass123!!";

let ipCounter = 0;
function fakeIp(): string {
  ipCounter += 1;
  return `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${ipCounter}`;
}

async function csrfHeader(page: Page): Promise<Record<string, string>> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "csrf_token")?.value;
  return csrf ? { "X-CSRF-Token": csrf } : {};
}

async function spoofIp(page: Page, pattern: string) {
  await page.route(pattern, (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
}

async function registerVerifyLogin(page: Page, email: string) {
  await spoofIp(page, "**/api/v1/auth/register");
  await spoofIp(page, "**/api/v1/auth/login");
  await page.goto("/register");
  await page.getByLabel(/full name/i).fill("Academic Tester");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByLabel(/confirm password/i).fill(PASSWORD);
  await page.getByLabel(/terms/i).check();
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: /check your email/i })).toBeVisible({
    timeout: 15000,
  });

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

  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/^password$/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/dashboard/, { timeout: 15000 });
}

async function apiGet<T>(page: Page, path: string): Promise<T> {
  const res = await page.request.get(`${BACKEND}/api/v1${path}`);
  expect(res.status(), `GET ${path}`).toBe(200);
  return (await res.json()).data as T;
}

async function apiCreate(page: Page, path: string, data: unknown): Promise<{ id: string }> {
  const res = await page.request.post(`${BACKEND}/api/v1${path}`, {
    data,
    headers: await csrfHeader(page),
  });
  expect(res.status(), `POST ${path}: ${await res.text()}`).toBe(201);
  return (await res.json()).data;
}

/** Opens the row menu ("Actions for <name>") and picks an item. */
async function rowAction(page: Page, rowName: string, item: string | RegExp) {
  await page.getByRole("button", { name: `Actions for ${rowName}`, exact: true }).click();
  await page.getByRole("menuitem", { name: item }).click();
}

/** Options are indented ("↳ Unit 1"), so match on the text they contain. */
async function pickMoveTarget(page: Page, name: string) {
  const value = await page
    .locator("#move-target option", { hasText: name })
    .first()
    .getAttribute("value");
  await page.locator("#move-target").selectOption(value!);
}

test.describe.configure({ mode: "serial" });

test.describe("Subjects, folders and chapters", () => {
  let page: Page;
  let email = "";
  let workspaceId = "";
  let subjectId = "";
  let base = "";
  const SUBJECT = "Calculus";

  test.beforeAll(async ({ browser }, testInfo) => {
    const tag = `${Date.now().toString(36)}${testInfo.project.name.replace(/\W/g, "").toLowerCase()}`;
    email = `academic-${tag}@example.com`;
    page = await browser.newPage();
    await registerVerifyLogin(page, email);
    await apiCreate(page, "/workspaces", {
      name: `Academic ${tag}`,
      workspace_type: "personal_learning",
    });
    // The dashboard quick action creates in the default workspace, so use that one throughout.
    const all = await apiGet<Array<{ id: string; is_default: boolean }>>(page, "/workspaces");
    workspaceId = (all.find((w) => w.is_default) ?? all[0]).id;
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("create a subject from the dashboard quick action", async () => {
    await page.goto("/dashboard");
    await page.getByRole("link", { name: "New subject" }).click();
    await expect(page).toHaveURL(/\/subjects\?create=1/);
    // ?create=1 opens the create dialog straight away.
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#subject-name").fill(SUBJECT);
    await page.locator("#subject-description").fill("Limits, derivatives, integrals");
    await page.getByRole("button", { name: "Create subject" }).click();
    await expect(page.getByRole("link", { name: SUBJECT })).toBeVisible({ timeout: 10000 });

    const subjects = await apiGet<Array<{ id: string; name: string }>>(
      page,
      `/workspaces/${workspaceId}/subjects`,
    );
    subjectId = subjects.find((s) => s.name === SUBJECT)!.id;
    base = `/workspaces/${workspaceId}/subjects/${subjectId}`;
    expect(subjectId).toBeTruthy();
  });

  test("search and sort the subject list", async () => {
    await apiCreate(page, `/workspaces/${workspaceId}/subjects`, { name: "Zoology" });
    await page.goto(`/subjects?workspace=${workspaceId}`);
    await page.locator("#subjects-sort").selectOption("name_desc");
    const names = page.getByRole("list", { name: "Subjects" }).getByRole("link");
    await expect(names.first()).toHaveText("Zoology");
    await page.locator("#subjects-search").fill("calc");
    await expect(names).toHaveCount(1);
    await expect(names.first()).toHaveText(SUBJECT);
  });

  test("the sidebar highlights Subjects, not My Workspace, on a subject page", async () => {
    await page.goto(`/workspaces/${workspaceId}/subjects/${subjectId}`);
    await expect(page.getByRole("heading", { name: SUBJECT })).toBeVisible();
    // On a phone the sidebar lives in a drawer behind the menu button.
    const menu = page.getByRole("button", { name: "Open menu" });
    if (await menu.isVisible()) await menu.click();
    const nav = page.getByRole("navigation").filter({ hasText: "Overview" }).first();
    await expect(nav.getByRole("link", { name: "Subjects" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(nav.getByRole("link", { name: "My Workspace" })).not.toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("heading", { name: /AI summaries and progress/ })).toContainText(
      "Coming soon",
    );
  });

  test("create folders and chapters", async () => {
    await page.goto(`/workspaces/${workspaceId}/subjects/${subjectId}`);
    await page.getByRole("button", { name: "New folder" }).first().click();
    await page.locator("#folder-name").fill("Unit 1");
    await page.getByRole("button", { name: "Create folder" }).click();
    await expect(page.getByText("Unit 1", { exact: true })).toBeVisible({ timeout: 10000 });

    for (const title of ["Limits", "Derivatives", "Integrals"]) {
      await page.getByRole("button", { name: "New chapter" }).first().click();
      await page.locator("#chapter-title").fill(title);
      await page.getByRole("button", { name: "Create chapter" }).click();
      await expect(page.getByRole("link", { name: title })).toBeVisible({ timeout: 10000 });
    }

    const chapters = await apiGet<Array<{ title: string }>>(page, `${base}/chapters`);
    expect(chapters.map((c) => c.title)).toEqual(["Limits", "Derivatives", "Integrals"]);
    await expect(page.getByText("1 folder")).toBeVisible();
    await expect(page.getByText("3 chapters")).toBeVisible();
  });

  test("a duplicate folder name shows the server error", async () => {
    await page.getByRole("button", { name: "New folder" }).first().click();
    await page.locator("#folder-name").fill("Unit 1");
    await page.getByRole("button", { name: "Create folder" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
  });

  test("reorder chapters with the up and down buttons", async () => {
    await page.getByRole("button", { name: "Move chapter Integrals up" }).click();
    await expect
      .poll(async () =>
        (await apiGet<Array<{ title: string }>>(page, `${base}/chapters`)).map((c) => c.title),
      )
      .toEqual(["Limits", "Integrals", "Derivatives"]);
    await expect(page.getByRole("button", { name: "Move chapter Limits up" })).toBeDisabled();
  });

  test("move a chapter into a folder", async () => {
    await rowAction(page, "chapter Derivatives", /move to folder/i);
    await pickMoveTarget(page, "Unit 1");
    await page.getByRole("button", { name: /^move$/i }).click();
    await expect
      .poll(async () => {
        const all = await apiGet<Array<{ title: string; folder_id: string | null }>>(
          page,
          `${base}/chapters`,
        );
        return all.find((c) => c.title === "Derivatives")?.folder_id ?? null;
      })
      .not.toBeNull();
  });

  test("move a folder under another and never offer itself", async () => {
    await page.getByRole("button", { name: "New folder" }).first().click();
    await page.locator("#folder-name").fill("Unit 2");
    await page.getByRole("button", { name: "Create folder" }).click();
    await expect(page.getByText("Unit 2", { exact: true })).toBeVisible({ timeout: 10000 });

    await rowAction(page, "folder Unit 2", /^move/i);
    const options = await page.locator("#move-target option").allTextContents();
    expect(options.some((o) => o.includes("Unit 2"))).toBe(false);
    await pickMoveTarget(page, "Unit 1");
    await page.getByRole("button", { name: /^move$/i }).click();
    await expect
      .poll(async () => {
        const folders = await apiGet<Array<{ name: string; parent_folder_id: string | null }>>(
          page,
          `${base}/folders?all_levels=true`,
        );
        return folders.find((f) => f.name === "Unit 2")?.parent_folder_id ?? null;
      })
      .not.toBeNull();
  });

  test("edit a chapter's status and see it on the chapter page", async () => {
    await page.getByRole("link", { name: "Limits" }).click();
    await expect(page.getByRole("heading", { name: "Limits" })).toBeVisible();
    await page.getByRole("button", { name: "Edit" }).click();
    await page.locator("#chapter-status").selectOption("in_progress");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("In progress").first()).toBeVisible({ timeout: 10000 });
    for (const tab of ["Learning materials", "AI explanations", "Flashcards", "Quizzes"]) {
      await expect(page.getByRole("tab", { name: tab })).toBeDisabled();
    }
    await expect(page.getByRole("navigation", { name: "You are here" })).toContainText(SUBJECT);
  });

  test("archive a chapter", async () => {
    await page.goto(`/workspaces/${workspaceId}/subjects/${subjectId}`);
    await rowAction(page, "chapter Integrals", "Archive");
    await expect(page.getByRole("link", { name: "Integrals" })).toHaveCount(0, { timeout: 10000 });
    const chapters = await apiGet<Array<{ title: string }>>(page, `${base}/chapters`);
    expect(chapters.map((c) => c.title)).not.toContain("Integrals");
  });

  test("deleting a non-empty folder needs a typed cascade confirmation", async () => {
    await rowAction(page, "folder Unit 1", "Delete");
    await page.getByRole("button", { name: "Delete folder", exact: true }).click();
    await expect(page.getByText(/is not empty/i)).toBeVisible();
    const confirm = page.getByRole("button", { name: /delete folder and everything inside/i });
    await expect(confirm).toBeDisabled();
    await page.locator("#confirm-text").fill("Unit 1");
    await confirm.click();
    await expect(page.getByText("Unit 1", { exact: true })).toHaveCount(0, { timeout: 10000 });
    const folders = await apiGet<Array<{ name: string }>>(page, `${base}/folders?all_levels=true`);
    expect(folders).toHaveLength(0);
    // D-12: the chapter that was inside Unit 1 is deleted too, not left loose.
    const chapters = await apiGet<Array<{ title: string }>>(page, `${base}/chapters`);
    expect(chapters.map((c) => c.title)).toEqual(["Limits"]);
  });

  test("a second user cannot see the first user's items", async ({ browser }) => {
    const ctx = await browser.newContext();
    const other = await ctx.newPage();
    await registerVerifyLogin(other, `other-${email}`);

    await other.goto(`/workspaces/${workspaceId}/subjects/${subjectId}`);
    await expect(other.getByText("Subject not found")).toBeVisible({ timeout: 10000 });
    await expect(other.getByText(SUBJECT)).toHaveCount(0);

    await other.goto("/subjects");
    await expect(other.getByText(SUBJECT)).toHaveCount(0);

    const res = await other.request.get(`${BACKEND}/api/v1${base}`);
    expect(res.status()).toBe(404);
    await ctx.close();
  });

  test("delete a subject names what will be deleted and needs its name typed", async () => {
    await page.goto(`/workspaces/${workspaceId}/subjects/${subjectId}`);
    await rowAction(page, `subject ${SUBJECT}`, "Delete subject");
    await expect(page.getByText(/permanently deletes the subject/i)).toBeVisible();
    await expect(page.getByRole("dialog").locator("strong")).toHaveText("0 folders and 1 chapter");
    const confirm = page.getByRole("button", { name: "Delete subject" });
    await expect(confirm).toBeDisabled();
    await page.locator("#confirm-text").fill(SUBJECT);
    await confirm.click();
    await expect(page).toHaveURL(/\/subjects\?workspace=/, { timeout: 10000 });
    const res = await page.request.get(`${BACKEND}/api/v1${base}`);
    expect(res.status()).toBe(404);
  });

  test("subject list and detail do not scroll sideways at 375px", async () => {
    const created = await apiCreate(page, `/workspaces/${workspaceId}/subjects`, {
      name: "A subject with quite a long name to stress the layout on a phone",
    });
    for (const path of [
      `/subjects?workspace=${workspaceId}`,
      `/workspaces/${workspaceId}/subjects/${created.id}`,
    ]) {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(overflow, `${path} scrolls horizontally`).toBe(false);
    }
  });
});
