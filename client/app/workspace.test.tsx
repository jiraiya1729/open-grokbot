import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Workspace } from "./workspace";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([]), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));
});

describe("Workspace", () => {
  it("shows an explicit create-Bot empty state", async () => {
    render(<Workspace />);
    expect(await screen.findByText("Your Bots will live here.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create your first bot/i })).toBeInTheDocument();
  });

  it("validates required Bot identity fields before calling the API", async () => {
    const user = userEvent.setup();
    render(<Workspace />);
    await screen.findByText("Your Bots will live here.");
    await user.click(screen.getByRole("button", { name: /create your first bot/i }));
    await user.click(screen.getByRole("button", { name: "Create Bot" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/name, primary job/i);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("opens global search palette with Ctrl+K", async () => {
    const user = userEvent.setup();
    render(<Workspace />);
    await screen.findByText("Your Bots will live here.");
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("textbox", { name: "Search workspace" })).toBeInTheDocument();
  });

  it("moves keyboard focus to Bot search with Ctrl+Shift+K", async () => {
    const user = userEvent.setup();
    render(<Workspace />);
    await screen.findByText("Your Bots will live here.");
    await user.keyboard("{Control>}{Shift>}k{/Shift}{/Control}");
    expect(screen.getByRole("textbox", { name: "Find a Bot" })).toHaveFocus();
  });
});
