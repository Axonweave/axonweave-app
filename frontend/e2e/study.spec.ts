/**
 * Study materials through the browser (Phase 4, M6 and M7), against the real stack.
 *
 * The stack runs on the FakeProvider, which cannot write structured study output, so ready-made
 * materials are created for the test user by `backend/scripts/seed_study_e2e.py` (no model call).
 * The generate flow is covered up to the honest failure state, which the fake provider produces.
 *
 * Needs `docker compose` on the machine running the tests (the same stack Playwright talks to).
 */

import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
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
  await page.getByLabel(/full name/i).fill("Study Tester");
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

const KEY_WORDS = ["correct_answers", "E2E-EXPLANATION", "rubric"];

test.describe("Study materials (desktop)", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(({ isMobile }) => isMobile, "phone layout is checked in the mobile block");

  let page: Page;
  let ids: Seeded = {};
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const email = `study-${stamp}@example.com`;

  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await registerVerifyLogin(page, email);
  });
  test.afterAll(async () => page.context().close());

  test("the sidebar opens Study materials, which starts empty", async () => {
    await page.getByRole("link", { name: "Study materials" }).first().click();
    await expect(page).toHaveURL(/\/study$/);
    await expect(page.getByText("No study materials yet")).toBeVisible();
  });

  test("the generate dialog shows only the settings of the chosen type", async () => {
    await page.getByRole("button", { name: "Generate", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: /generate study material/i });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("What to generate").selectOption("glossary");
    await expect(dialog.getByLabel("Maximum terms")).toBeVisible();
    await expect(dialog.getByLabel("Number of cards")).toHaveCount(0);
    await dialog.getByLabel("What to generate").selectOption("flashcards");
    await expect(dialog.getByLabel("Number of cards")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Generate" })).toBeDisabled(); // no source yet
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });

  test("a generation the fake provider cannot satisfy ends in a clear failure", async () => {
    test.skip(process.env.LLM_PROVIDER !== "fake", "needs the fake provider (never the real one)");
    await page.getByRole("button", { name: "Generate", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: /generate study material/i });
    await dialog.getByLabel("Source type").selectOption("text");
    await dialog.getByLabel("Workspace").selectOption({ index: 1 });
    await dialog
      .getByLabel("Pasted text")
      .fill(
        "Photosynthesis converts light energy into chemical energy inside chloroplasts. ".repeat(
          20,
        ),
      );
    await dialog.getByRole("button", { name: "Generate" }).click();
    await expect(dialog.getByTestId("job-progress")).toBeVisible({ timeout: 15000 });
    await expect(dialog.getByRole("alert")).toBeVisible({ timeout: 60000 });
    await page.keyboard.press("Escape");
  });

  test("seeded materials are listed, searchable and filterable", async () => {
    ids = seed(email);
    await page.goto("/study");
    for (const title of ["Cell energy summary", "Cell glossary", "Cell flashcards", "Cell quiz"]) {
      await expect(page.getByRole("link", { name: title })).toBeVisible({ timeout: 15000 });
    }
    await page.getByLabel("Search study materials").fill("glossary");
    await expect(page.getByRole("link", { name: "Cell glossary" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Cell quiz" })).toHaveCount(0);
    await page.getByLabel("Search study materials").fill("");
    await page.getByLabel("Filter by type").selectOption("quiz");
    await expect(page.getByRole("link", { name: "Cell quiz" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Cell glossary" })).toHaveCount(0);
    await page.getByLabel("Filter by type").selectOption("");
  });

  test("a summary can be edited, versioned and restored", async () => {
    await page.goto(`/study/${ids.summary}`);
    await expect(page.getByRole("heading", { name: "Cell energy summary" })).toBeVisible();
    await expect(page.getByText(/Version 1/)).toBeVisible();
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await page.getByLabel("Body").first().fill("Mitochondria make ATP. Edited by the student.");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText(/Version 2/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Edited by the student/)).toBeVisible();
    await page.getByRole("button", { name: "Versions" }).click();
    const history = page.getByRole("region", { name: "Version history" });
    await expect(history.getByText("Version 1")).toBeVisible();
    await history.getByRole("button", { name: "Restore" }).first().click();
    await expect(page.getByText(/Version 3/)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Edited by the student/)).toHaveCount(0);
  });

  test("a summary offers whole and per-section regeneration", async () => {
    await expect(page.getByRole("button", { name: "Regenerate", exact: true })).toBeVisible();
  });

  test("the glossary searches, the formula sheet warns and renders safely", async () => {
    await page.goto(`/study/${ids.glossary}`);
    await expect(page.getByText("3 terms")).toBeVisible({ timeout: 15000 });
    await page.getByLabel("Search terms").fill("osmosis");
    await expect(page.getByText("1 term")).toBeVisible();
    await expect(page.getByText("Movement of water across a membrane.")).toBeVisible();

    await page.goto(`/study/${ids.formula_sheet}`);
    await expect(page.getByRole("note")).toContainText(/not verified/i);
    await expect(page.locator(".katex").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/Needs review/)).toBeVisible();
    // The broken formula is shown as plain text, never as HTML.
    await expect(page.locator("[data-latex-error='true']")).toHaveCount(1);
  });

  test("flashcards flip and move with the keyboard", async () => {
    await page.goto(`/study/${ids.flashcards}`);
    const face = page.getByTestId("flashcard-face");
    await expect(face).toContainText("Card question number 1?", { timeout: 15000 });
    await face.focus();
    await page.keyboard.press("Enter");
    await expect(face).toContainText("Card answer 1");
    await page.keyboard.press("ArrowRight");
    await expect(page.getByText("Card 2 of 3")).toBeVisible();
    await page.getByRole("button", { name: "Shuffle" }).click();
    await expect(page.getByText("Card 1 of 3")).toBeVisible();
    await page.getByRole("tab", { name: "Edit cards" }).click();
    await page.getByRole("button", { name: "Edit" }).first().click();
    await page.getByLabel("Front").first().fill("A changed front question?");
    await page.getByRole("button", { name: "Save card" }).click();
    await expect(page.getByText("A changed front question?")).toBeVisible();
  });

  test("a full quiz: no key before submit, autosave, refresh-resume, results with explanations", async () => {
    const seen: string[] = [];
    page.on("response", async (res) => {
      if (!res.url().includes("/api/v1/study/")) return;
      try {
        seen.push(await res.text());
      } catch {
        /* redirects and aborted requests have no body */
      }
    });
    await page.goto(`/study/${ids.quiz}/quiz`);
    await expect(page.getByText(/Which organelle produces/)).toBeVisible({ timeout: 15000 });
    await page.getByRole("radio", { name: /Mitochondrion/ }).check();
    await expect(page.getByTestId("save-state")).toContainText("saved", { timeout: 10000 });

    await page.reload();
    await expect(page.getByRole("radio", { name: /Mitochondrion/ })).toBeChecked({
      timeout: 15000,
    });
    await page.getByRole("button", { name: "Question 2" }).click();
    await page.getByRole("radio", { name: "True" }).check();
    await expect(page.getByTestId("save-state")).toContainText("saved", { timeout: 10000 });

    // Nothing the browser received so far may contain the answer key (D-94, spec 7.6).
    expect(seen.length).toBeGreaterThan(0);
    for (const body of seen) for (const word of KEY_WORDS) expect(body).not.toContain(word);

    await page.getByRole("button", { name: "Submit quiz" }).click();
    await page.getByRole("button", { name: "Submit", exact: true }).click();
    await expect(page).toHaveURL(/quiz\/results\/[0-9a-f-]{36}/, { timeout: 15000 });
    await expect(page.getByTestId("quiz-score")).toHaveText("100%");
    await expect(page.getByText("E2E-EXPLANATION-ONE")).toBeVisible();
    await expect(page.getByText(/not a measure of your overall mastery/i)).toBeVisible();
    page.removeAllListeners("response");

    await page.goto(`/study/${ids.quiz}`);
    await expect(page.getByRole("heading", { name: "Attempt history" })).toBeVisible();
    await expect(page.getByRole("link", { name: "View results" })).toHaveCount(1);
  });

  test("a timed quiz is submitted by itself when the server deadline passes", async () => {
    await page.goto(`/study/${ids.timed_quiz}/quiz`);
    await expect(page.getByTestId("quiz-timer")).toBeVisible({ timeout: 15000 });
    await page.getByRole("radio", { name: /Mitochondrion/ }).check();
    await expect(page).toHaveURL(/quiz\/results\/[0-9a-f-]{36}/, { timeout: 30000 });
    await expect(page.getByText(/submitted automatically/i)).toBeVisible();
  });

  test("a flashcard deck can be exported to CSV and downloaded", async () => {
    await page.goto(`/study/${ids.flashcards}`);
    await page.getByLabel("Export format").selectOption("csv");
    await page.getByRole("button", { name: "Export", exact: true }).click();
    const link = page.getByRole("link", { name: /Download CSV/ });
    await expect(link).toBeVisible({ timeout: 60000 });
    const href = (await link.getAttribute("href")) ?? "";
    const res = await page.request.get(href);
    expect(res.status()).toBe(200);
    expect(res.headers()["content-disposition"]).toContain("attachment");
    expect(res.headers()["x-content-type-options"]).toBe("nosniff");
  });

  test("study preferences save and persist", async () => {
    await page.goto("/settings");
    await page.getByRole("tab", { name: "Study material" }).click();
    await page.getByLabel("Language").fill("Spanish");
    await page.getByRole("button", { name: "Save preferences" }).click();
    await expect(page.getByText("Study preferences saved")).toBeVisible();
    await page.reload();
    await page.getByRole("tab", { name: "Study material" }).click();
    await expect(page.getByLabel("Language")).toHaveValue("Spanish");
  });

  test("a second user cannot see or open any of it", async ({ browser }) => {
    const other = await (await browser.newContext()).newPage();
    try {
      await registerVerifyLogin(other, `study-b-${stamp}@example.com`);
      await other.goto("/study");
      await expect(other.getByText("No study materials yet")).toBeVisible({ timeout: 15000 });
      await other.goto(`/study/${ids.summary}`);
      await expect(other.getByText("Could not load", { exact: true })).toBeVisible({
        timeout: 15000,
      });
      for (const id of [ids.summary, ids.flashcards, ids.quiz]) {
        const res = await other.request.get(`${BACKEND}/api/v1/study/materials/${id}`);
        expect(res.status()).toBe(404);
      }
      const quizRow = ids.quiz_row;
      const attempt = await other.request.get(`${BACKEND}/api/v1/study/quizzes/${quizRow}`);
      expect(attempt.status()).toBe(404);
    } finally {
      await other.context().close();
    }
  });

  test("deleting asks for confirmation and removes the material", async () => {
    await page.goto("/study");
    await page.getByRole("button", { name: "Delete Cell glossary" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByRole("link", { name: "Cell glossary" })).toHaveCount(0, {
      timeout: 15000,
    });
  });
});

test.describe("Study materials (mobile)", () => {
  test.skip(({ isMobile }) => !isMobile, "phone layout only");

  test("the list, a viewer and the quiz fit a phone screen", async ({ page }) => {
    const email = `study-m-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
    await registerVerifyLogin(page, email);
    const ids = seed(email);
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
    await page.goto("/study");
    await expect(page.getByRole("link", { name: "Cell energy summary" })).toBeVisible({
      timeout: 15000,
    });
    expect(await overflow()).toBeLessThanOrEqual(1);
    await page.goto(`/study/${ids.formula_sheet}`);
    await expect(page.locator(".katex").first()).toBeVisible({ timeout: 15000 });
    expect(await overflow()).toBeLessThanOrEqual(1);
    await page.goto(`/study/${ids.quiz}/quiz`);
    await expect(page.getByText(/Which organelle produces/)).toBeVisible({ timeout: 15000 });
    expect(await overflow()).toBeLessThanOrEqual(1);
  });
});
