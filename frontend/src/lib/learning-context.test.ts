import { describe, expect, it } from "vitest";
import {
  activeTab,
  appliedScope,
  contextFromQuery,
  contextQuery,
  environmentBase,
  environmentHref,
  makeContext,
  toConversationScope,
} from "./learning-context";

const W = "11111111-1111-1111-1111-111111111111";
const S = "22222222-2222-2222-2222-222222222222";
const F = "33333333-3333-3333-3333-333333333333";
const C = "44444444-4444-4444-4444-444444444444";

describe("makeContext", () => {
  it("takes its scope from the deepest id", () => {
    expect(makeContext({ workspaceId: W }).scope).toBe("workspace");
    expect(makeContext({ workspaceId: W, subjectId: S }).scope).toBe("subject");
    expect(makeContext({ workspaceId: W, subjectId: S, folderId: F }).scope).toBe("folder");
    expect(makeContext({ workspaceId: W, subjectId: S, folderId: F, chapterId: C }).scope).toBe(
      "chapter",
    );
  });

  it("ignores folder and chapter ids without a subject", () => {
    const ctx = makeContext({ workspaceId: W, folderId: F, chapterId: C });
    expect(ctx).toEqual({
      workspaceId: W,
      subjectId: undefined,
      folderId: undefined,
      chapterId: undefined,
      scope: "workspace",
    });
  });
});

describe("environment URLs", () => {
  const subject = makeContext({ workspaceId: W, subjectId: S });
  const folder = makeContext({ workspaceId: W, subjectId: S, folderId: F });
  const chapter = makeContext({ workspaceId: W, subjectId: S, chapterId: C });

  it("builds one base per level", () => {
    expect(environmentBase(subject)).toBe(`/workspaces/${W}/subjects/${S}`);
    expect(environmentBase(folder)).toBe(`/workspaces/${W}/subjects/${S}/folders/${F}`);
    expect(environmentBase(chapter)).toBe(`/workspaces/${W}/subjects/${S}/chapters/${C}`);
    expect(environmentBase(makeContext({ workspaceId: W }))).toBeNull();
  });

  it("puts every tab under the same base", () => {
    expect(environmentHref(folder)).toBe(`/workspaces/${W}/subjects/${S}/folders/${F}`);
    expect(environmentHref(folder, "graph")).toBe(
      `/workspaces/${W}/subjects/${S}/folders/${F}/graph`,
    );
    expect(environmentHref(chapter, "tutor")).toBe(
      `/workspaces/${W}/subjects/${S}/chapters/${C}/tutor`,
    );
  });

  it("sends workspace scope to the global tools", () => {
    const ws = makeContext({ workspaceId: W });
    expect(environmentHref(ws, "graph")).toBe("/knowledge");
    expect(environmentHref(ws, "content")).toBe(`/subjects?workspace=${W}`);
  });

  it("reads the active tab back from a pathname", () => {
    const base = environmentBase(subject)!;
    expect(activeTab(base, base)).toBe("overview");
    expect(activeTab(`${base}/revision`, base)).toBe("revision");
    expect(activeTab(`${base}/unknown`, base)).toBe("overview");
  });
});

describe("query hand-off", () => {
  it("round-trips a context", () => {
    const ctx = makeContext({ workspaceId: W, subjectId: S, folderId: F });
    expect(contextFromQuery(new URLSearchParams(contextQuery(ctx)))).toEqual(ctx);
  });

  it("rejects values that are not id-shaped", () => {
    expect(contextFromQuery(new URLSearchParams("ws=<script>"))).toBeNull();
    const ctx = contextFromQuery(new URLSearchParams(`ws=${W}&subject=../../etc`));
    expect(ctx).toEqual(makeContext({ workspaceId: W }));
  });

  it("returns null without a workspace", () => {
    expect(contextFromQuery(new URLSearchParams(`subject=${S}`))).toBeNull();
  });
});

describe("toConversationScope", () => {
  it("uses the deepest level as the tutor's primary context", () => {
    expect(toConversationScope(makeContext({ workspaceId: W }))).toEqual({
      kind: "workspace",
      id: W,
    });
    expect(
      toConversationScope(makeContext({ workspaceId: W, subjectId: S, chapterId: C })),
    ).toEqual({ kind: "chapter", id: C });
  });
});

describe("appliedScope", () => {
  const folder = makeContext({ workspaceId: W, subjectId: S, folderId: F });
  const chapter = makeContext({ workspaceId: W, subjectId: S, chapterId: C });

  it("keeps the tutor at any level", () => {
    expect(appliedScope("tutor", folder)).toEqual({ applied: folder, widened: false });
  });

  it("widens tools that cannot filter by folder, and says so", () => {
    const graph = appliedScope("graph", folder);
    expect(graph.widened).toBe(true);
    expect(graph.applied.scope).toBe("subject");
    expect(graph.applied.subjectId).toBe(S);
    expect(graph.applied.folderId).toBeUndefined();
  });

  it("keeps chapter filtering where the API supports it", () => {
    expect(appliedScope("progress", chapter).widened).toBe(false);
    expect(appliedScope("revision", chapter).applied.chapterId).toBe(C);
  });

  it("puts research at workspace level", () => {
    const r = appliedScope("research", chapter);
    expect(r.applied.scope).toBe("workspace");
    expect(r.widened).toBe(true);
  });
});
