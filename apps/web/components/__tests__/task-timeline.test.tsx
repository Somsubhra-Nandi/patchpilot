import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TaskTimeline } from "../task-timeline";

describe("TaskTimeline", () => {
  it("renders events and simulated evidence", () => {
    render(<TaskTimeline events={[{ id: "e1", task_id: "t1", event_type: "validation.completed", stage: "tests_run", summary: "Validation completed", details: { simulated: true }, channel: "telegram", actor: "patchpilot", created_at: "2026-08-06T10:00:00Z" }]} />);
    expect(screen.getByText("Validation completed")).toBeInTheDocument();
    expect(screen.getByText("simulated")).toBeInTheDocument();
    expect(screen.getByText("telegram")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<TaskTimeline events={[]} />);
    expect(screen.getByText("No timeline events yet")).toBeInTheDocument();
  });
});

