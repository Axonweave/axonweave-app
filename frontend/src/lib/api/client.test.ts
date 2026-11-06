import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiRequestError } from "./client";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client requests", () => {
  it("always sends credentials so the session cookie is included", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: 1 }));
    await api.get("/x");
    expect(lastCall().init.credentials).toBe("include");
  });

  it("targets the versioned API base path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: null }));
    await api.get("/workspaces");
    expect(lastCall().url).toMatch(/\/api\/v1\/workspaces$/);
  });

  it("echoes the csrf_token cookie in X-CSRF-Token on every state-changing method", async () => {
    document.cookie = "csrf_token=token%20value; path=/";
    fetchMock.mockImplementation(async () => jsonResponse({ success: true, data: null }));

    await api.post("/x", { a: 1 });
    expect(lastCall().headers.get("X-CSRF-Token")).toBe("token value");
    await api.patch("/x", {});
    expect(lastCall().headers.get("X-CSRF-Token")).toBe("token value");
    await api.put("/x", {});
    expect(lastCall().headers.get("X-CSRF-Token")).toBe("token value");
    await api.delete("/x");
    expect(lastCall().headers.get("X-CSRF-Token")).toBe("token value");
  });

  it("does not send the CSRF header on GET", async () => {
    document.cookie = "csrf_token=abc; path=/";
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: null }));
    await api.get("/x");
    expect(lastCall().headers.get("X-CSRF-Token")).toBeNull();
  });

  it("omits the header (rather than sending an empty one) when there is no cookie", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: null }));
    await api.post("/x", {});
    expect(lastCall().headers.has("X-CSRF-Token")).toBe(false);
  });

  it("serialises the body as JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: null }));
    await api.post("/x", { name: "Uni" });
    expect(lastCall().init.body).toBe(JSON.stringify({ name: "Uni" }));
    expect(lastCall().headers.get("Content-Type")).toBe("application/json");
  });
});

describe("api client responses", () => {
  it("returns the parsed success envelope", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, data: { id: "1" }, total: 3 }));
    const res = await api.get<{ id: string }>("/x");
    expect(res.data).toEqual({ id: "1" });
    expect((res as unknown as { total: number }).total).toBe(3);
  });

  it("turns an error envelope into an ApiRequestError with code, message and status", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          success: false,
          error: { code: "RESOURCE_NOT_FOUND", message: "Nope", details: { a: 1 } },
        },
        404,
      ),
    );
    const err = await api.get("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect(err).toMatchObject({
      code: "RESOURCE_NOT_FOUND",
      message: "Nope",
      status: 404,
      details: { a: 1 },
    });
  });

  it("reports a PARSE_ERROR when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>oops</html>", { status: 502 }));
    await expect(api.get("/x")).rejects.toMatchObject({ code: "PARSE_ERROR", status: 502 });
  });

  it("treats 204 No Content as success with null data", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.delete("/x")).resolves.toEqual({ success: true, data: null });
  });

  it("lets network failures propagate", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.get("/x")).rejects.toThrow("Failed to fetch");
  });
});
