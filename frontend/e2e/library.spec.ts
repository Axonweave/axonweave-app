/**
 * Library and document-grounded AI Tutor through the browser, against the real stack (worker,
 * object store, Redis) with the FAKE LLM and no embedding provider (keyword search only).
 *
 * Flow: upload -> processing -> ready -> read it -> ask about it -> second user cannot see it ->
 * delete. Account setup uses the Mailpit flow of the other specs.
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "LibraryPass123!!";
const NOTES =
  "Photosynthesis happens in chloroplasts. The light reactions take place in the thylakoid membranes.";

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
  await page.getByLabel(/full name/i).fill("Library Tester");
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

/** A one-page PDF with real text, built in code (no copyrighted files, D-76). */
function makePdf(text: string): Buffer {
  const NL = String.fromCharCode(10);
  const stream = `BT /F1 18 Tf 72 700 Td (${text}) Tj ET`;
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>${NL}stream${NL}${stream}${NL}endstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = `%PDF-1.4${NL}`;
  const offsets: number[] = [];
  objs.forEach((o, k) => {
    offsets.push(out.length);
    out += `${k + 1} 0 obj${NL}${o}${NL}endobj${NL}`;
  });
  const xref = out.length;
  out += `xref${NL}0 ${objs.length + 1}${NL}0000000000 65535 f ${NL}`;
  offsets.forEach((o) => (out += `${String(o).padStart(10, "0")} 00000 n ${NL}`));
  out += `trailer${NL}<< /Size ${objs.length + 1} /Root 1 0 R >>${NL}startxref${NL}${xref}${NL}%%EOF${NL}`;
  return Buffer.from(out, "latin1");
}

test.describe("Library and document answers (desktop)", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(({ isMobile }) => isMobile, "layout is covered by the component tests");

  let page: Page;
  let documentUrl = "";
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const name = `bio-${stamp}.txt`;

  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await registerVerifyLogin(page, `library-${stamp}@example.com`);
  });
  test.afterAll(async () => page.context().close());

  test("the sidebar opens the Library, which starts empty", async () => {
    await page.getByRole("link", { name: "Library" }).click();
    await expect(page).toHaveURL(/\/library$/);
    await expect(page.getByText("No documents yet")).toBeVisible();
  });

  test("an uploaded text file is processed to Ready", async () => {
    await page.getByLabel("Choose files to upload").setInputFiles({
      name,
      mimeType: "text/plain",
      buffer: Buffer.from(NOTES),
    });
    const row = page.getByRole("listitem").filter({ hasText: name });
    await expect(row).toBeVisible({ timeout: 15000 });
    await expect(row.getByText("Ready", { exact: true })).toBeVisible({ timeout: 90000 });
  });

  test("the document page shows its extracted text", async () => {
    await page.getByRole("link", { name }).click();
    await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}/);
    documentUrl = page.url();
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await expect(page.getByText(/happens in chloroplasts/)).toBeVisible({ timeout: 15000 });
  });

  test("the AI Tutor answers from the document and does not give up", async () => {
    await page.goto("/ai-tutor");
    const notice = page.getByRole("dialog", { name: /before you start/i });
    // The notice loads asynchronously; wait briefly for it instead of checking once.
    const shown = await notice
      .waitFor({ state: "visible", timeout: 8000 })
      .then(() => true)
      .catch(() => false);
    if (shown) await notice.getByRole("button", { name: /i understand/i }).click();
    await page.getByRole("combobox", { name: /ask about/i }).selectOption("document");
    await page.getByLabel("Choose what to ask about").selectOption({ label: name });
    const box = page.getByRole("textbox", { name: /message the ai tutor/i });
    await box.fill("Where does photosynthesis happen?");
    await box.press("Enter");
    const answer = page.locator('[data-role="assistant"]').last();
    await expect(answer).toHaveAttribute("data-status", "completed", { timeout: 30000 });
    await expect(answer).not.toContainText("could not find enough");
  });

  test("a cited PDF passage is highlighted on its page", async () => {
    test.setTimeout(150000);
    const pdfName = `cited-${stamp}.pdf`;
    await page.goto("/library");
    const input = page.getByLabel("Choose files to upload");
    await expect(input).toBeEnabled({ timeout: 15000 }); // enabled once a workspace is known
    await input.setInputFiles({
      name: pdfName,
      mimeType: "application/pdf",
      buffer: makePdf("Mitochondria produce ATP through oxidative phosphorylation"),
    });
    const row = page.getByRole("listitem").filter({ hasText: pdfName });
    await expect(row.getByText("Ready", { exact: true })).toBeVisible({ timeout: 90000 });
    const href = await row.getByRole("link", { name: pdfName }).getAttribute("href");
    const id = href!.split("/").pop()!;
    const csrf = (await page.context().cookies()).find((c) => c.name === "csrf_token")?.value ?? "";
    const found = await page.request.post(`${BACKEND}/api/v1/search`, {
      headers: { "X-CSRF-Token": csrf },
      data: { query: "mitochondria ATP", mode: "keyword", scope: { kind: "document", id } },
    });
    expect(found.ok()).toBeTruthy();
    const hit = (await found.json()).data.results[0];
    await page.goto(`/documents/${id}?page=${hit.page_number ?? 1}&source=${hit.chunk_id}`);
    await expect(page.getByTestId("cited-region").first()).toBeVisible({ timeout: 30000 });
  });

  test("a second user cannot open or see the document", async ({ browser }) => {
    const other = await (await browser.newContext()).newPage();
    try {
      await registerVerifyLogin(other, `library-b-${stamp}@example.com`);
      await other.goto(documentUrl);
      await expect(other.getByText("Could not load", { exact: true })).toBeVisible({
        timeout: 15000,
      });
      const id = documentUrl.split("/").pop()!;
      const res = await other.request.get(`${BACKEND}/api/v1/documents/${id}`);
      expect(res.status()).toBe(404);
    } finally {
      await other.context().close();
    }
  });

  test("deleting asks for confirmation and removes the document", async () => {
    await page.goto("/library");
    await page.getByRole("button", { name: `Delete ${name}` }).click();
    await page.getByRole("button", { name: "Delete permanently" }).click();
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0, { timeout: 15000 });
    const id = documentUrl.split("/").pop()!;
    const res = await page.request.get(`${BACKEND}/api/v1/documents/${id}`);
    expect(res.status()).toBe(404);
  });
});

test.describe("Library (mobile)", () => {
  test.skip(({ isMobile }) => !isMobile, "phone layout only");

  test("the Library fits a phone screen and offers upload", async ({ page }) => {
    await registerVerifyLogin(
      page,
      `library-m-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`,
    );
    await page.goto("/library");
    await expect(page.getByText("No documents yet")).toBeVisible({ timeout: 15000 });
    await expect(page.getByLabel("Choose files to upload")).toBeAttached();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
