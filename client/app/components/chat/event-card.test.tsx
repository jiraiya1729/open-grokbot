import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Approval, ProductEvent } from "@/lib/types";
import { EventCard } from "./event-card";

const event = (event_type: string, payload: Record<string, unknown> = {}): ProductEvent => ({
  id: 1,
  run_id: "run-1",
  sequence: 1,
  event_type,
  payload,
  created_at: "2026-09-18T00:00:00Z",
});

describe("EventCard registry", () => {
  it.each([
    ["tool_activity", { label: "Running command", status: "running" }, "Running command"],
    ["artifact_created", { name: "Result.md" }, "Created Result.md"],
    ["computer_activity", { label: "Computer ready", status: "running" }, "Computer ready"],
    ["takeover_requested", { status: "active" }, "You took control"],
    ["steering", { status: "applied", text: "Use the shorter format" }, "Steering applied"],
    ["run_error", { message: "Provider unavailable", code: "provider" }, "Provider unavailable"],
  ])("renders %s", (type, payload, text) => {
    render(<EventCard event={event(type, payload)} onResolveApproval={vi.fn()} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("renders an understandable unknown-event fallback", () => {
    render(<EventCard event={event("future_event")} onResolveApproval={vi.fn()} />);
    expect(screen.getByText("Activity update")).toBeInTheDocument();
    expect(screen.getByText("future event")).toBeInTheDocument();
  });

  it("shows exact approval payload and resolves the exact record", () => {
    const approval: Approval = {
      id: "approval-1", run_id: "run-1", bot_id: "bot-1", action_type: "publish",
      action_payload: { target: "release notes" }, action_digest: "a".repeat(64), status: "pending",
      requested_at: "2026-09-18T00:00:00Z", resolved_at: null, resolution_note: null,
    };
    const resolve = vi.fn();
    render(<EventCard event={event("approval_requested", { approval_id: approval.id })} approval={approval} onResolveApproval={resolve} />);
    expect(screen.getByText(/release notes/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve exact action" }));
    expect(resolve).toHaveBeenCalledWith(approval, "approved");
  });
});
