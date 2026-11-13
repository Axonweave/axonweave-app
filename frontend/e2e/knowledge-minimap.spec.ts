/**
 * Knowledge graph minimap, against the real stack.
 *
 * Regression for: the minimap drew no nodes (an empty grey box with a tiny frame) because the
 * controlled graph never fed xyflow's measurements back into its node objects. The checks compare
 * the minimap's viewport frame with the main canvas's real zoom/pan transform, so they fail if the
 * two ever disagree, and they drive the real interactions (zoom, pan, click, drag, resize).
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const MAILPIT = process.env.MAILPIT_API ?? "http://localhost:8025/api/v1";
const PASSWORD = "MinimapPass123!!";
const NODES = 14;

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
  await page.getByLabel(/full name/i).fill("Minimap Tester");
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

async function api<T>(page: Page, method: "GET" | "POST", path: string, data?: unknown) {
  const res =
    method === "GET"
      ? await page.request.get(`${BACKEND}/api/v1${path}`)
      : await page.request.post(`${BACKEND}/api/v1${path}`, { data, headers: await csrf(page) });
  expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
  return (res.status() === 204 ? null : (await res.json()).data) as T;
}

/** A hub-and-chain graph that is wider than the canvas, so the viewport is a real sub-area. */
async function seedGraph(page: Page): Promise<{ workspaceId: string; ids: string[] }> {
  const workspaces = await api<Array<{ id: string }>>(page, "GET", "/workspaces");
  const workspaceId = workspaces[0].id;
  const ids: string[] = [];
  for (let i = 0; i < NODES; i += 1) {
    const node = await api<{ id: string }>(page, "POST", "/knowledge/nodes", {
      workspace_id: workspaceId,
      name: `Concept ${i + 1}`,
      node_type: i % 3 === 0 ? "topic" : "concept",
    });
    ids.push(node.id);
  }
  for (let i = 1; i < NODES; i += 1) {
    await api(page, "POST", "/knowledge/relationships", {
      source_node_id: ids[i < 7 ? 0 : i - 1],
      target_node_id: ids[i],
      relationship_type: i % 2 ? "PART_OF" : "RELATED_TO",
    });
  }
  return { workspaceId, ids };
}

interface View {
  x: number;
  y: number;
  w: number;
  h: number;
}
interface State {
  zoom: number;
  expected: View; // what the main canvas is really showing, from its own transform
  frame: View | null; // the minimap's viewport frame
  box: { x: number; y: number; w: number; h: number };
  viewBox: View;
  svg: { x: number; y: number; w: number; h: number };
  miniNodes: number;
  container: { x: number; y: number; w: number; h: number };
  controls: { x: number; y: number; w: number; h: number } | null;
}

async function state(page: Page): Promise<State> {
  return page.evaluate(() => {
    const rect = (el: Element | null) => {
      const r = el?.getBoundingClientRect();
      return r ? { x: r.x, y: r.y, w: r.width, h: r.height } : null;
    };
    const flow = document.querySelector(".react-flow") as HTMLElement;
    const viewport = document.querySelector(".react-flow__viewport") as HTMLElement | null;
    const svg = document.querySelector(".react-flow__minimap-svg") as SVGElement | null;
    if (!flow || !viewport || !svg) {
      // the canvas is not mounted yet (first load or right after a reload)
      const none = { x: 0, y: 0, w: 0, h: 0 };
      return {
        zoom: 1,
        expected: none,
        frame: null,
        box: none,
        viewBox: none,
        svg: none,
        miniNodes: 0,
        container: none,
        controls: null,
      };
    }
    const m = new DOMMatrixReadOnly(getComputedStyle(viewport).transform);
    const container = rect(flow)!;
    const [vx, vy, vw, vh] = (svg.getAttribute("viewBox") ?? "0 0 0 0").split(/\s+/).map(Number);
    const d = document.querySelector(".react-flow__minimap-mask")?.getAttribute("d") ?? "";
    const subpaths = [...d.matchAll(/M(-?[\d.e+-]+),(-?[\d.e+-]+)h(-?[\d.e+-]+)v(-?[\d.e+-]+)/g)];
    const f = subpaths[1];
    return {
      zoom: m.a,
      expected: { x: -m.e / m.a, y: -m.f / m.a, w: container.w / m.a, h: container.h / m.a },
      frame: f ? { x: +f[1], y: +f[2], w: +f[3], h: +f[4] } : null,
      box: rect(document.querySelector(".react-flow__minimap"))!,
      viewBox: { x: vx, y: vy, w: vw, h: vh },
      svg: rect(svg)!,
      miniNodes: document.querySelectorAll(".react-flow__minimap-node").length,
      container,
      controls: rect(document.querySelector(".react-flow__controls")),
    };
  });
}

function near(a: number, b: number, tol = 1.5) {
  expect(Math.abs(a - b), `${a} vs ${b}`).toBeLessThanOrEqual(tol);
}

/** The minimap frame must equal what the main canvas is actually showing. */
async function expectSynced(page: Page) {
  await expect
    .poll(
      async () => {
        const s = await state(page);
        if (!s.frame) return false;
        const tol = Math.max(2, 2 / s.zoom);
        return (
          Math.abs(s.frame.x - s.expected.x) <= tol &&
          Math.abs(s.frame.y - s.expected.y) <= tol &&
          Math.abs(s.frame.w - s.expected.w) <= tol &&
          Math.abs(s.frame.h - s.expected.h) <= tol
        );
      },
      { timeout: 5000, message: "minimap frame does not match the main canvas viewport" },
    )
    .toBe(true);
}

const center = (v: View) => ({ x: v.x + v.w / 2, y: v.y + v.h / 2 });

test.describe("Knowledge graph minimap", () => {
  test.setTimeout(180_000);

  test("draws the graph, follows zoom and pan, and navigates by click and drag", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "pointer-precise desktop checks");
    const email = `minimap-${Date.now()}@example.com`;
    await registerVerifyLogin(page, email);
    const { ids } = await seedGraph(page);

    await page.goto("/knowledge");
    const map = page.getByTestId("rf__minimap");
    await expect(map).toBeVisible({ timeout: 20000 });

    // 1. it draws every node (the original bug drew none), inside a proportionate frame
    await expect.poll(async () => (await state(page)).miniNodes).toBe(NODES);
    await page.waitForTimeout(600); // initial fit-view animation
    let s = await state(page);
    expect(s.frame, "viewport frame is drawn").not.toBeNull();
    expect(s.frame!.w).toBeGreaterThan(s.viewBox.w * 0.25); // not a speck inside a big box
    await expectSynced(page);

    // 2. placement and size: bottom-right of the graph container, compact, clear of controls
    s = await state(page);
    expect(s.box.w).toBeLessThanOrEqual(220);
    expect(s.box.h).toBeLessThanOrEqual(160);
    expect(s.box.x + s.box.w).toBeLessThanOrEqual(s.container.x + s.container.w);
    expect(s.box.y + s.box.h).toBeLessThanOrEqual(s.container.y + s.container.h);
    expect(s.container.x + s.container.w - (s.box.x + s.box.w)).toBeLessThan(40);
    expect(s.container.y + s.container.h - (s.box.y + s.box.h)).toBeLessThan(40);
    if (s.controls) expect(s.controls.x + s.controls.w).toBeLessThan(s.box.x);

    // 3. zoom in and out with the controls: the frame follows immediately
    const startZoom = s.zoom;
    await page.getByRole("button", { name: "Zoom in" }).click();
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect.poll(async () => (await state(page)).zoom).toBeGreaterThan(startZoom);
    await expectSynced(page);
    s = await state(page);
    const zoomedFrameW = s.frame!.w;
    await page.getByRole("button", { name: "Zoom out" }).click();
    await page.getByRole("button", { name: "Zoom out" }).click();
    await page.getByRole("button", { name: "Zoom out" }).click();
    await expectSynced(page);
    s = await state(page);
    expect(s.frame!.w).toBeGreaterThan(zoomedFrameW); // zooming out shows more of the graph

    // 4. pan the main canvas in all four directions
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expectSynced(page);
    const pane = page.locator(".react-flow__pane");
    const box = (await pane.boundingBox())!;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    for (const [dx, dy] of [
      [120, 0],
      [-240, 0],
      [0, 100],
      [0, -200],
    ]) {
      const before = center((await state(page)).frame!);
      await page.mouse.move(cx, cy);
      await page.mouse.down();
      await page.mouse.move(cx + dx, cy + dy, { steps: 8 });
      await page.mouse.up();
      await expectSynced(page);
      const after = center((await state(page)).frame!);
      // dragging the canvas right moves the visible window left, and so on
      if (dx) expect(Math.sign(after.x - before.x)).toBe(-Math.sign(dx));
      if (dy) expect(Math.sign(after.y - before.y)).toBe(-Math.sign(dy));
    }

    // 5. clicking a spot on the minimap centres the main view on that spot
    s = await state(page);
    const targets = [
      { fx: 0.15, fy: 0.2 },
      { fx: 0.85, fy: 0.75 },
    ];
    for (const t of targets) {
      s = await state(page);
      const px = s.svg.x + s.svg.w * t.fx;
      const py = s.svg.y + s.svg.h * t.fy;
      const wantX = s.viewBox.x + s.viewBox.w * t.fx;
      const wantY = s.viewBox.y + s.viewBox.h * t.fy;
      await page.mouse.click(px, py);
      await expect
        .poll(
          async () => {
            const c = center((await state(page)).expected);
            return Math.hypot(c.x - wantX, c.y - wantY);
          },
          { timeout: 5000, message: "view did not centre on the clicked minimap point" },
        )
        .toBeLessThan(Math.max(6, 6 / s.zoom));
      await expectSynced(page);
    }

    // 6. dragging inside the minimap pans the main view in step
    s = await state(page);
    const fromC = center(s.expected);
    const sx = s.svg.x + s.svg.w / 2;
    const sy = s.svg.y + s.svg.h / 2;
    await page.mouse.move(sx, sy);
    await page.mouse.down();
    await page.mouse.move(sx - 40, sy - 20, { steps: 8 });
    await page.mouse.up();
    await expectSynced(page);
    const toC = center((await state(page)).expected);
    expect(toC.x, "dragging the minimap left pans the view toward the left of the graph").not.toBe(
      fromC.x,
    );
    near(Math.sign(toC.x - fromC.x), -1, 0.01);

    // 7. node set changes: add one concept, then remove it
    const workspaceId = (await api<Array<{ id: string }>>(page, "GET", "/workspaces"))[0].id;
    const extra = await api<{ id: string }>(page, "POST", "/knowledge/nodes", {
      workspace_id: workspaceId,
      name: "Late concept",
      node_type: "concept",
    });
    await api(page, "POST", "/knowledge/relationships", {
      source_node_id: ids[0],
      target_node_id: extra.id,
      relationship_type: "PART_OF",
    });
    await page.reload();
    await expect
      .poll(async () => (await state(page)).miniNodes, { timeout: 20000 })
      .toBe(NODES + 1);
    await page.waitForTimeout(600);
    await expectSynced(page);
    await api(page, "POST", `/knowledge/nodes/${extra.id}/archive`);
    await page.request.delete(`${BACKEND}/api/v1/knowledge/nodes/${extra.id}`, {
      headers: await csrf(page),
    });
    await page.reload();
    await expect.poll(async () => (await state(page)).miniNodes, { timeout: 20000 }).toBe(NODES);
    await page.waitForTimeout(600);
    await expectSynced(page);

    // 8. resizing the window keeps the minimap in step and inside its container
    await page.setViewportSize({ width: 1000, height: 700 });
    await page.waitForTimeout(400);
    await expectSynced(page);
    s = await state(page);
    expect(s.box.x + s.box.w).toBeLessThanOrEqual(s.container.x + s.container.w + 0.5);
    await page.setViewportSize({ width: 600, height: 700 }); // narrow: a smaller minimap, still shown
    await page.waitForTimeout(400);
    await expectSynced(page);
    s = await state(page);
    expect(s.box.w).toBeLessThan(160);
    expect(s.miniNodes).toBe(NODES);
    expect(s.box.x + s.box.w).toBeLessThanOrEqual(s.container.x + s.container.w + 0.5);
    await page.setViewportSize({ width: 1400, height: 900 });
    await page.waitForTimeout(400);
    await expectSynced(page);
    s = await state(page);
    expect(s.box.w).toBeGreaterThan(160);
  });
});
