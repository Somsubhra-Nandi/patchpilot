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

  it("surfaces proposed validation commands and skipped checks", () => {
    render(<TaskTimeline events={[{ id: "e2", task_id: "t1", event_type: "validation.plan_proposed", stage: "tests_run", summary: "Validation plan proposed by Codex", details: { proposed_validation_plan: { commands_to_run: ["pytest tests/test_parser.py -q"], checks_skipped: [{ command_or_check: "pytest -q", reason: "Targeted coverage is sufficient." }], rationale: "Parser test maps directly to the changed source.", relevant_test_files: ["tests/test_parser.py"], validation_scope: "targeted", confidence: "high" } }, channel: null, actor: "codex", created_at: "2026-08-06T10:00:00Z" }]} />);
    expect(screen.getByText("pytest tests/test_parser.py -q")).toBeInTheDocument();
    expect(screen.getByText(/Targeted coverage is sufficient/)).toBeInTheDocument();
  });
});

