import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test-utils";
import TaskDetailPage from "../page";

vi.mock("next/navigation", () => ({ useParams: () => ({ taskId: "task-1" }) }));
vi.mock("@/lib/api", () => ({ API_URL: "http://api", api: {
  task: vi.fn().mockResolvedValue({ id: "task-1", repository_id: "r1", github_issue_number: 151, github_issue_url: "https://github.com/octo/demo/issues/151", title: "Retry webhook delivery", description: "Add operator guidance", status: "awaiting_approval", current_stage: "approval_requested", origin_channel: "slack", origin_sender: "maya", origin_conversation_id: "C1", assigned_maintainer: "Maya", branch_name: null, pull_request_url: null, failure_reason: null, created_at: "2026-08-06T10:00:00Z", updated_at: "2026-08-06T10:00:00Z", completed_at: null, repository: { id: "r1", name: "demo", owner: "octo", full_name: "octo/demo", github_url: "https://github.com/octo/demo", default_branch: "main", test_command: "pytest", lint_command: "ruff", protected_paths: [], coding_guidelines: null, autonomy_level: "approval_required", created_at: "2026-08-06T10:00:00Z", updated_at: "2026-08-06T10:00:00Z" }, events: [{ id: "e1", task_id: "task-1", event_type: "plan.generated", stage: "plan_generated", summary: "Plan ready", details: { plan: { issue_summary: "Retry webhook delivery", suspected_change: "Classify transient failures", relevant_files: ["src/retry.py"], proposed_modifications: ["Add retry hint"], validation_strategy: ["pytest"], risks: [], open_questions: [], confidence: "medium" } }, channel: null, actor: "patchpilot", created_at: "2026-08-06T10:00:00Z" }], approvals: [{ id: "a1", approval_type: "implementation_plan", status: "pending", requested_channel: "slack", requested_from: "Maya", responded_channel: null, responded_by: null, response_note: null, created_at: "2026-08-06T10:00:00Z", responded_at: null }], decisions: [] }),
  decide: vi.fn(),
  resolveDecision: vi.fn(),
  taskAction: vi.fn(),
} }));

class EventSourceStub {
  addEventListener() {}
  close() {}
}

beforeAll(() => { vi.stubGlobal("EventSource", EventSourceStub); });

describe("TaskDetailPage", () => {
  it("shows approval controls and rejection dialog", async () => {
    renderWithQuery(<TaskDetailPage />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Retry webhook delivery", level: 1 })).toBeInTheDocument());
    expect(screen.getAllByText("Approve plan").length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByText("Reject")[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Reject implementation plan?")).toBeInTheDocument();
  });
});
