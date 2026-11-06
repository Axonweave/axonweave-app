import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AsyncSection } from "./async-section";

function setup(props: Partial<React.ComponentProps<typeof AsyncSection>> = {}) {
  return render(
    <AsyncSection
      title="Things"
      loading={false}
      error={null}
      isEmpty={false}
      empty={<p>Nothing here</p>}
      {...props}
    >
      <p>The data</p>
    </AsyncSection>,
  );
}

describe("AsyncSection", () => {
  it("shows a spinner while loading", () => {
    setup({ loading: true });
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.queryByText("The data")).not.toBeInTheDocument();
  });

  it("shows the error with a working retry", async () => {
    const onRetry = vi.fn();
    setup({ error: "Boom", onRetry });
    expect(screen.getByText("Boom")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows the empty state", () => {
    setup({ isEmpty: true });
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("shows the data and labels the region by its heading", () => {
    setup();
    expect(screen.getByText("The data")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Things" })).toBeInTheDocument();
  });
});
