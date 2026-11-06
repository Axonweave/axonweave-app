/**
 * AI Tutor through the browser, against the real stack with the FAKE provider.
 *
 * The fake provider echoes the last user message ("Test reply to: ...") and can pause between
 * chunks (FAKE_LLM_CHUNK_DELAY_SECONDS), so streaming and Stop are deterministic and free.
 * Run the stack with LLM_PROVIDER=fake (CI does). Never run this against a real provider key.
 *
 * Account setup uses the same Mailpit flow as the other specs; everything else is done in the UI,
 * and the API is used only to read state back.
 */

import { expect, test } from "@playwright/test";
import type { Browser, Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "AiTutorPass123!!";

let ipCounter = 0;
function fakeIp(): string {
  ipCounter += 1;
  return `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.${ipCounter}`;
}

async function spoofIp(page: Page, pattern: string) {
  await page.route(pattern, (route) =>
    route.continue({ headers: { ...route.request().headers(), "x-forwarded-for": fakeIp() } }),
  );
}

async function registerVerifyLogin(page: Page, email: string) {
  await spoofIp(page, "**/api/v1/auth/register");
  await spoofIp(page, "**/api/v1/auth/login");
  await spoofIp(page, "**/api/v1/auth/verify-email");
  await page.goto("/register");
  await page.getByLabel(/full name/i).fill("Tutor Tester");
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

async function csrf(page: Page): Promise<Record<string, string>> {
  const token = (await page.context().cookies()).find((c) => c.name === "csrf_token")?.value;
  return token ? { "X-CSRF-Token": token } : {};
}

async function apiGet<T>(page: Page, path: string, expected = 200): Promise<T> {
  const res = await page.request.get(`${BACKEND}/api/v1${path}`);
  expect(res.status(), `GET ${path}`).toBe(expected);
  return (await res.json()).data as T;
}

async function apiPost<T>(page: Page, path: string, data: unknown): Promise<T> {
  const res = await page.request.post(`${BACKEND}/api/v1${path}`, {
    data,
    headers: await csrf(page),
  });
  expect(res.status(), `POST ${path}: ${await res.text()}`).toBeLessThan(300);
  return (await res.json()).data as T;
}

interface Msg {
  id: string;
  role: string;
  content: string;
  status: string;
  superseded_at: string | null;
}

async function messages(page: Page, conversationId: string): Promise<Msg[]> {
  return apiGet<Msg[]>(page, `/ai/conversations/${conversationId}/messages?limit=100`);
}

function conversationIdOf(page: Page): string {
  const id = new URL(page.url()).pathname.split("/").pop();
  expect(id).toMatch(/^[0-9a-f-]{36}$/);
  return id!;
}

const input = (page: Page) => page.getByRole("textbox", { name: /message the ai tutor/i });
const assistantMessages = (page: Page) => page.locator('[data-role="assistant"]');

async function sendMessage(page: Page, text: string) {
  // Enter is ignored while an answer is still being generated (the Send button becomes Stop), so
  // wait for the previous turn to finish first, as a real user would. Matters on slow CI runners.
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible({ timeout: 20000 });
  await input(page).fill(text);
  await input(page).press("Enter");
}

/** ~190 chars: the fake provider echoes up to 200, in 8-char chunks, so this streams for ~2 s. */
const LONG =
  "Explain how a neural network learns from data, covering weights, loss, gradients and backpropagation in plain words please. "
    .repeat(2)
    .slice(0, 190);

async function acknowledgeNotice(page: Page) {
  const dialog = page.getByRole("dialog", { name: /before you start/i });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/test provider/i);
  await dialog.getByRole("button", { name: /i understand/i }).click();
  await expect(dialog).toBeHidden();
}

// ── desktop flow ─────────────────────────────────────────────────────────────

test.describe("AI Tutor (desktop)", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(({ isMobile }) => isMobile, "covered by the mobile layout tests below");

  let page: Page;
  let conversationId = "";
  const email = `tutor-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

  test.beforeAll(async ({ browser }) => {
    page = await (await browser.newContext()).newPage();
    await registerVerifyLogin(page, email);
  });
  test.afterAll(async () => page.context().close());

  test("the sidebar link opens the AI Tutor and shows the one-time privacy notice", async () => {
    await page.getByRole("link", { name: "AI Tutor" }).click();
    await expect(page).toHaveURL(/\/ai-tutor$/);
    // Nothing can be used before the notice is acknowledged.
    await acknowledgeNotice(page);
    await expect(page.getByRole("heading", { name: "Welcome to Axonweave AI" })).toBeVisible();
    await expect(page.getByTestId("test-provider-badge")).toBeVisible();
    // It is stored server-side, so it does not come back after a reload.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Welcome to Axonweave AI" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: /before you start/i })).toBeHidden();
    const prefs = await apiGet<{ ai_notice_acknowledged_at: string | null }>(
      page,
      "/users/me/preferences",
    );
    expect(prefs.ai_notice_acknowledged_at).not.toBeNull();
  });

  test("a suggested prompt sends a real request and creates a conversation", async () => {
    await page.getByRole("button", { name: "Explain a difficult concept" }).click();
    await expect(page).toHaveURL(/\/ai-tutor\/[0-9a-f-]{36}$/, { timeout: 15000 });
    conversationId = conversationIdOf(page);
    await expect(assistantMessages(page).first()).toContainText("Test reply to:", {
      timeout: 15000,
    });
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.");
    const stored = await messages(page, conversationId);
    expect(stored.map((m) => [m.role, m.status])).toEqual([
      ["user", "completed"],
      ["assistant", "completed"],
    ]);
  });

  test("the conversation appears in the sidebar with a title and is highlighted", async () => {
    const link = page.getByRole("navigation", { name: "Conversations" }).getByRole("link", {
      name: /Explain a difficult concept/i,
    });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("aria-current", "page");
  });

  test("text streams in progressively, with Stop shown meanwhile, then completes", async () => {
    await page.getByRole("link", { name: "New chat" }).first().click();
    await expect(page.getByRole("heading", { name: "Welcome to Axonweave AI" })).toBeVisible();
    await sendMessage(page, LONG);
    await expect(page).toHaveURL(/\/ai-tutor\/[0-9a-f-]{36}$/, { timeout: 15000 });

    const reply = assistantMessages(page).first();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    // Real text (not the "Thinking…" placeholder) shows up before the answer is finished.
    await expect(reply).toContainText("Test reply to:", { timeout: 10000 });
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    const partial = (await reply.innerText()).trim();
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.", {
      timeout: 20000,
    });
    const final = (await reply.innerText()).trim();
    expect(final.length).toBeGreaterThan(partial.length);
    await expect(page.getByRole("button", { name: "Stop" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
    // Streamed text is never inside a live region (it would flood screen readers).
    await expect(page.locator('[aria-live] [data-role="assistant"]')).toHaveCount(0);
  });

  test("Stop cancels the answer, keeps what arrived and records a cancelled request", async () => {
    await page.getByRole("link", { name: "New chat" }).first().click();
    await sendMessage(page, LONG);
    await expect(page).toHaveURL(/\/ai-tutor\/[0-9a-f-]{36}$/, { timeout: 15000 });
    const id = conversationIdOf(page);

    const stop = page.getByRole("button", { name: "Stop" });
    await expect(stop).toBeVisible();
    // Wait for real streamed text (not the "Thinking…" placeholder) so Stop lands mid-stream.
    await expect(assistantMessages(page).first()).toContainText("Test reply to:", {
      timeout: 10000,
    });
    await stop.click();

    await expect(page.getByText(/stopped before the answer finished/i)).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
    const stored = await messages(page, id);
    const assistant = stored.find((m) => m.role === "assistant")!;
    expect(assistant.status).toBe("cancelled");
    expect(assistant.content.length).toBeGreaterThan(0);
    expect(assistant.content.length).toBeLessThan(LONG.length + 20);

    const usage = await apiGet<{ request_status: string }[]>(page, "/ai/usage?status=cancelled");
    expect(usage.length).toBeGreaterThanOrEqual(1);
    // A stopped answer can be regenerated.
    await page.getByRole("button", { name: "Regenerate" }).first().click();
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.", {
      timeout: 20000,
    });
  });

  test("follow-up questions work in the same conversation", async () => {
    await page.getByRole("link", { name: /Explain a difficult concept/i }).click();
    // Wait for the route to change: until then the previous conversation (which also has one
    // answer) is still on screen, and a send would be dropped by the switch.
    await expect(page).toHaveURL(new RegExp(`/ai-tutor/${conversationId}$`));
    await expect(page.locator('[data-role="user"]')).toContainText("Explain a difficult concept");
    await expect(assistantMessages(page)).toHaveCount(1);
    await sendMessage(page, "And now a follow up question");
    await expect(assistantMessages(page)).toHaveCount(2, { timeout: 15000 });
    await expect(assistantMessages(page).nth(1)).toContainText("follow up question", {
      timeout: 15000,
    });
    conversationId = conversationIdOf(page);
    const stored = await messages(page, conversationId);
    expect(stored.map((m) => m.role)).toEqual(["user", "assistant", "user", "assistant"]);
  });

  test("after a refresh the whole history is still there, from the server", async () => {
    await page.reload();
    await expect(page.locator('[data-role="user"]')).toHaveCount(2);
    await expect(assistantMessages(page)).toHaveCount(2);
    await expect(assistantMessages(page).nth(1)).toContainText("follow up question");
  });

  test("Enter sends and Shift+Enter inserts a new line", async () => {
    const box = input(page);
    await box.fill("line one");
    await box.press("Shift+Enter");
    await box.type("line two");
    await expect(box).toHaveValue("line one\nline two");
    await box.fill("");
  });

  test("regenerate replaces the latest answer and supersedes the old one", async () => {
    const before = await messages(page, conversationId);
    const oldAnswer = before.filter((m) => m.role === "assistant" && !m.superseded_at).at(-1)!;
    await page.getByRole("button", { name: "Regenerate" }).last().click();
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.", {
      timeout: 20000,
    });
    await expect(assistantMessages(page)).toHaveCount(2);
    const after = await messages(page, conversationId);
    expect(after.find((m) => m.id === oldAnswer.id)?.superseded_at).not.toBeNull();
    expect(after.filter((m) => m.role === "assistant" && !m.superseded_at)).toHaveLength(2);
  });

  test("thumbs up and down are saved", async () => {
    const good = page.getByRole("button", { name: "Good response" }).last();
    const saved = page.waitForResponse(
      (r) => r.url().includes("/feedback") && r.request().method() === "POST",
    );
    await good.click();
    expect((await saved).status()).toBe(200);
    await expect(good).toHaveAttribute("aria-pressed", "true");
  });

  test("copy puts the answer on the clipboard", async () => {
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: /^Copy/ }).last().click();
    await expect(page.getByRole("button", { name: /Copied/ }).first()).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("Test reply to:");
  });

  test("model output is rendered safely: hostile HTML never runs", async () => {
    await page.getByRole("link", { name: "New chat" }).first().click();
    await sendMessage(
      page,
      'x <img src=x onerror="window.__pwned=1"> <script>window.__pwned=2</script> [bad](javascript:window.__pwned=3)',
    );
    await expect(assistantMessages(page).first()).toContainText("Test reply to:", {
      timeout: 15000,
    });
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.");
    expect(
      await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
    ).toBeUndefined();
    await expect(assistantMessages(page).first().locator("img, script, iframe")).toHaveCount(0);
    const hrefs = await assistantMessages(page)
      .first()
      .locator("a")
      .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""));
    for (const href of hrefs) expect(href).not.toMatch(/^javascript:/i);
  });

  test("rename updates the sidebar, the header and the server", async () => {
    await page.getByRole("link", { name: /Explain a difficult concept/i }).click();
    await page.getByRole("button", { name: /Actions for Explain a difficult concept/i }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    const title = page.getByLabel("Title");
    await title.fill("Photosynthesis notes");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(
      page
        .getByRole("navigation", { name: "Conversations" })
        .getByRole("link", { name: "Photosynthesis notes" }),
    ).toBeVisible();
    await expect(page.getByTestId("conversation-title")).toHaveText("Photosynthesis notes");
    const conv = await apiGet<{ title: string }>(page, `/ai/conversations/${conversationId}`);
    expect(conv.title).toBe("Photosynthesis notes");
  });

  test("search filters the conversation list", async () => {
    const search = page.getByRole("searchbox", { name: "Search conversations" });
    await search.fill("Photosynthesis");
    const nav = page.getByRole("navigation", { name: "Conversations" });
    await expect(nav.getByRole("link", { name: "Photosynthesis notes" })).toBeVisible();
    await expect(nav.getByRole("link")).toHaveCount(1);
    await search.fill("zzz-no-such-conversation");
    await expect(nav.getByText(/no conversations match/i)).toBeVisible();
    await search.fill("");
  });

  test("usage shows real figures, and 'Unknown' (never 0) for cost", async () => {
    await page.getByRole("button", { name: "AI usage" }).click();
    const dialog = page.getByRole("dialog", { name: /ai usage/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Estimated cost")).toBeVisible();
    await expect(dialog.getByText("Unknown")).toBeVisible();
    const summary = await apiGet<{ requests: number }>(page, "/ai/usage/summary");
    await expect(dialog).toContainText(String(summary.requests));
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("archive removes it from the list; delete asks first and removes it for good", async () => {
    // Archive a throwaway conversation.
    const arch = await apiPost<{ id: string }>(page, "/ai/conversations", { title: "To archive" });
    await page.goto("/ai-tutor");
    await page.getByRole("button", { name: /Actions for To archive/i }).click();
    await page.getByRole("menuitem", { name: "Archive" }).click();
    await expect(page.getByRole("link", { name: "To archive" })).toBeHidden();
    expect((await apiGet<{ status: string }>(page, `/ai/conversations/${arch.id}`)).status).toBe(
      "archived",
    );

    // Delete the main one, cancelling first.
    await page.getByRole("link", { name: "Photosynthesis notes" }).click();
    await page.getByRole("button", { name: /Actions for Photosynthesis notes/i }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    const confirm = page.getByRole("alertdialog");
    await expect(confirm).toContainText(/permanently deleted/i);
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("link", { name: "Photosynthesis notes" })).toBeVisible();

    await page.getByRole("button", { name: /Actions for Photosynthesis notes/i }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
    await expect(page).toHaveURL(/\/ai-tutor$/);
    await expect(page.getByRole("link", { name: "Photosynthesis notes" })).toBeHidden();
    await apiGet(page, `/ai/conversations/${conversationId}`, 404);
  });

  test("another user cannot open this user's conversation", async ({ browser }) => {
    const mine = await apiPost<{ id: string }>(page, "/ai/conversations", {
      title: "Private chat",
    });
    await apiPost(page, `/ai/conversations/${mine.id}/messages`, {
      content: "secret question",
      stream: false,
    });

    const other = await newUser(browser);
    await other.goto(`/ai-tutor/${mine.id}`);
    await acknowledgeNotice(other);
    await expect(other.getByText("Conversation not found")).toBeVisible();
    await expect(other.getByText("secret question")).toHaveCount(0);
    await expect(other.getByText("Private chat")).toHaveCount(0);
    await apiGet(other, `/ai/conversations/${mine.id}`, 404);
    await other.context().close();
  });
});

async function newUser(browser: Browser): Promise<Page> {
  const p = await (await browser.newContext()).newPage();
  await registerVerifyLogin(
    p,
    `tutor-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`,
  );
  return p;
}

// ── mobile layout ────────────────────────────────────────────────────────────

test.describe("AI Tutor (mobile, 375px)", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(({ isMobile }) => !isMobile, "mobile project only");
  test.use({ viewport: { width: 375, height: 667 } });

  let page: Page;
  const email = `tutor-m-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

  const overflow = () =>
    page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );

  test.beforeAll(async ({ browser }) => {
    page = await (
      await browser.newContext({
        viewport: { width: 375, height: 667 },
        isMobile: true,
        hasTouch: true,
      })
    ).newPage();
    await registerVerifyLogin(page, email);
    await page.goto("/ai-tutor");
    await acknowledgeNotice(page);
  });
  test.afterAll(async () => page.context().close());

  test("the welcome screen fits without horizontal scrolling", async () => {
    await expect(page.getByRole("heading", { name: "Welcome to Axonweave AI" })).toBeVisible();
    expect(await overflow()).toBeLessThanOrEqual(0);
    await expect(input(page)).toBeVisible();
  });

  test("the conversation list is a drawer that opens, traps focus and closes", async () => {
    await expect(page.getByRole("navigation", { name: "Conversations" })).toBeHidden();
    await page.getByRole("button", { name: "Open conversations" }).click();
    const drawer = page.getByRole("dialog", { name: "Conversations" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "New chat" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(page.getByRole("button", { name: "Open conversations" })).toBeFocused();
  });

  test("a long code block and wide table scroll inside the message, not the page", async () => {
    await sendMessage(
      page,
      "x\n\n```\n" + "A".repeat(150) + "\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |",
    );
    await expect(page).toHaveURL(/\/ai-tutor\/[0-9a-f-]{36}$/, { timeout: 15000 });
    await expect(page.getByTestId("chat-announcer")).toHaveText("Response complete.", {
      timeout: 20000,
    });
    await expect(page.locator("pre").first()).toBeVisible();
    expect(await overflow()).toBeLessThanOrEqual(0);
    const box = await page.locator("pre").first().boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(376);
  });

  test("a chosen conversation opens from the drawer and the drawer closes", async () => {
    await page
      .getByRole("link", { name: "New chat" })
      .first()
      .click()
      .catch(() => undefined);
    await page.getByRole("button", { name: "Open conversations" }).click();
    const drawer = page.getByRole("dialog", { name: "Conversations" });
    await drawer.getByRole("link").nth(1).click();
    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/\/ai-tutor\/[0-9a-f-]{36}$/);
    expect(await overflow()).toBeLessThanOrEqual(0);
  });
});
