import { describe, expect, it } from "vitest";
import { activityHref, describeActivity } from "./activity";

describe("describeActivity", () => {
  it("builds a readable sentence from real log fields", () => {
    expect(
      describeActivity({ action: "created", entity_type: "workspace", entity_name: "Uni" }),
    ).toBe("Created workspace “Uni”");
  });

  it("omits the name when none was recorded", () => {
    expect(describeActivity({ action: "archived", entity_type: "folder", entity_name: null })).toBe(
      "Archived folder",
    );
  });

  it("capitalises unknown actions instead of hiding them", () => {
    expect(describeActivity({ action: "moved", entity_type: "chapter", entity_name: "A" })).toBe(
      "Moved chapter “A”",
    );
  });
});

describe("activityHref", () => {
  it("does not link deleted entities", () => {
    expect(activityHref({ entity_type: "subject", entity_status: "deleted" })).toBeNull();
  });

  it("sends archived entities to the archived page", () => {
    expect(activityHref({ entity_type: "chapter", entity_status: "archived" })).toBe("/archived");
  });

  it("links active workspaces and academic items to their pages", () => {
    expect(activityHref({ entity_type: "workspace", entity_status: "active" })).toBe("/workspaces");
    expect(activityHref({ entity_type: "folder", entity_status: "active" })).toBe("/subjects");
  });
});
