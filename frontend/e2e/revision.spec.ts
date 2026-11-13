/**
 * Phase 5 through the browser: quiz history and compare, revision sessions, progress and the
 * dashboard widget, against the real stack.
 *
 * Materials come from `backend/scripts/seed_study_e2e.py` (no model call). Quiz attempts are made
 * through the UI so the history, analytics and calendar show real data. The first attempt answers
 * wrongly and the second correctly, so the comparison has something to show.
 */

import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "StudyPass123!!";
const REPO_ROOT = path.resolve(__dirname, "../..");

let ipCounter = 0;
const fakeIp = () =>
  `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${(ipCounter += 1)}`;

async function spoofIp(page: Page, pattern: string) {
  await page.route(pattern, (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
}

async function registerVerifyLogin(page: Page, email: string) {
  for (const p of ["register", "login", "verify-email"]) await spoofIp(page, `**/api/v1/auth/${p}`);
  await page.goto("/register");
  await page.getByLabel(/full name/i).fill("Revision Tester");
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

type Seeded = Record<string, string>;
function seed(email: string): Seeded {
  const out = execFileSync(
    "docker",
    ["compose", "exec", "-T", "backend", "python", "scripts/seed_study_e2e.py", email],
    { cwd: REPO_ROOT, encoding: "utf8" },
  );
  return JSON.parse(out.trim().split("\n").pop() ?? "{}");
}

async function takeQuiz(page: Page, quizMaterialId: string, right: boolean) {
  await page.goto(`/study/${quizMaterialId}/quiz`);
  await expect(page.getByText(/Which organelle produces/)).toBeVisible({ timeout: 15000 });
  await page.getByRole("radio", { name: right ? /Mitochondrion/ : /Ribosome/ }).check();
  await expect(page.getByTestId("save-state")).toContainText("saved", { timeout: 10000 });
  await page.getByRole("button", { name: "Question 2" }).click();
  await page.getByRole("radio", { name: right ? "True" : "False" }).check();
  await expect(page.getByTestId("save-state")).toContainText("saved", { timeout: 10000 });
  await page.getByRole("button", { name: "Submit quiz" }).click();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page).toHaveURL(/quiz\/results\/[0-9a-f-]{36}/, { timeout: 15000 });
  await expect(page.getByTestId("quiz-score")).toHaveText(right ? "100%" : "0%");
}

test.describe("Assessment and revision (desktop)", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(({ isMobile }) => isMobile, "phone layout is checked in the mobile block");

  let page: Page;
  let ids: Seeded = {};
  const email = `revision-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await registerVerifyLogin(page, email);
    ids = seed(email);
  });
  test.afterAll(async () => page.context().close());

  test("a new user sees honest empty states on the progress page", async () => {
    // before any attempt exists, the page must not invent numbers
    await page.goto("/progress");
    await expect(page.getByRole("heading", { name: "Progress" })).toBeVisible();
    await expect(page.getByText(/No study activity yet/)).toBeVisible({ timeout: 15000 });
  });

  test("two quiz attempts appear in the history and can be compared", async () => {
    await takeQuiz(page, ids.quiz, false);
    await takeQuiz(page, ids.quiz, true);

    await page.goto("/study/history");
    await expect(page.getByRole("heading", { name: "Quiz history" })).toBeVisible();
    await expect(page.getByRole("link", { name: "View results" })).toHaveCount(2, {
      timeout: 15000,
    });

    const compare = page.getByRole("button", { name: "Compare selected" });
    await expect(compare).toBeDisabled();
    const boxes = page.getByRole("checkbox");
    await boxes.nth(0).check();
    await boxes.nth(1).check();
    await expect(compare).toBeEnabled();
    await compare.click();

    await expect(page.getByRole("heading", { name: "Attempt comparison" })).toBeVisible();
    await expect(page.getByText("Improved").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("+100 pts").first()).toBeVisible();

    // the status filter narrows the list without a page reload
    await page.getByLabel("Status").selectOption("in_progress");
    await expect(page.getByText(/No quiz attempts match/)).toBeVisible();
  });

  test("the date filters narrow the history, and the end date includes that whole day", async () => {
    const day = (offset: number) =>
      new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
    await page.goto("/study/history");
    const rows = page.getByRole("link", { name: "View results" });
    await expect(rows).toHaveCount(2, { timeout: 15000 });

    await page.getByLabel("From").fill(day(1));
    await expect(page.getByText(/No quiz attempts match/)).toBeVisible();

    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(rows).toHaveCount(2);

    // attempts made today (UTC) must still be listed when "To" is today
    await page.getByLabel("To").fill(day(0));
    await expect(rows).toHaveCount(2);
    await page.getByLabel("To").fill(day(-1));
    await expect(page.getByText(/No quiz attempts match/)).toBeVisible();
  });

  test("a history row opens that attempt's results", async () => {
    await page.goto("/study/history");
    await page.getByRole("link", { name: "View results" }).first().click();
    await expect(page).toHaveURL(/quiz\/results\/[0-9a-f-]{36}/);
    await expect(page.getByTestId("quiz-score")).toBeVisible({ timeout: 15000 });
  });

  test("a revision session runs with the keyboard and finishes", async () => {
    await page.goto("/revision");
    const start = page.getByRole("button", { name: "Start revision session" });
    await expect(start).toBeEnabled({ timeout: 15000 });
    await expect(page.getByText(/3 cards in total/)).toBeVisible();
    await start.click();

    await expect(page).toHaveURL(/\/revision\/session\/[0-9a-f-]{36}/, { timeout: 15000 });
    for (let n = 1; n <= 3; n++) {
      await expect(page.getByText(`Card ${n} of 3`)).toBeVisible({ timeout: 15000 });
      await page.keyboard.press("Space");
      await expect(page.getByRole("button", { name: /Good/ })).toBeVisible();
      await page.keyboard.press("3");
    }
    await expect(page.getByTestId("session-complete")).toBeVisible({ timeout: 15000 });

    await page.goto("/revision");
    // Newly learned cards can legitimately be due again later today, so only the review count is
    // asserted: each of the 3 cards was rated once.
    const reviewed = page.getByText("Reviewed today").locator("xpath=following-sibling::p");
    await expect(reviewed).toHaveText("3", { timeout: 15000 });
  });

  test("the progress page shows scores, trends and the calendar from real activity", async () => {
    await page.goto("/progress");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Average quiz score")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Subject", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Subjects" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Trends" })).toBeVisible();
    await expect(page.getByRole("img", { name: /Quiz scores over time/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Study calendar" })).toBeVisible();

    // today's cell is active and opens its details
    const today = page.getByRole("button", { name: /: 2 quizzes, 3 cards reviewed/ });
    await expect(today).toBeVisible();
    await today.click();
    await expect(
      page.getByText(/2 quiz attempts · 1 revision sessions · 3 cards reviewed/),
    ).toBeVisible();

    await page.getByRole("link", { name: /quiz history and compare/ }).click();
    await expect(page).toHaveURL(/\/study\/history/);
  });

  test("the dashboard shows the revision widget with real numbers", async () => {
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Revision", exact: true })).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText("Current streak")).toBeVisible();
    await expect(page.getByText("Due today")).toBeVisible();
    await page.getByRole("link", { name: "Open revision" }).click();
    await expect(page).toHaveURL(/\/revision$/);
  });

  test("another user cannot see this user's attempts", async ({ browser }) => {
    const other = await (await browser.newContext()).newPage();
    await registerVerifyLogin(
      other,
      `revision-other-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`,
    );
    await other.goto("/study/history");
    await expect(other.getByText(/No quiz attempts match/)).toBeVisible({ timeout: 15000 });
    await other.context().close();
  });
});

test.describe("Assessment and revision (phone)", () => {
  test.skip(({ isMobile }) => !isMobile, "desktop is covered above");

  test("progress, history and revision fit a phone screen", async ({ page }) => {
    await registerVerifyLogin(
      page,
      `revision-mobile-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`,
    );
    for (const route of ["/progress", "/study/history", "/revision", "/dashboard"]) {
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15000 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${route} scrolls sideways`).toBeLessThanOrEqual(1);
    }
  });
});
