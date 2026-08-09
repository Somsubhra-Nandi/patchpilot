import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test-utils";
import DashboardPage from "../page";

vi.mock("@/lib/api", () => ({ api: {
  tasks: vi.fn().mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [{ id: "33333333-3333-4333-8333-333333333333", repository_id: "r1", github_issue_number: 151, github_issue_url: "https://github.com/octo/demo/issues/151", title: "Add retry guidance", description: "Demo", status: "awaiting_approval", current_stage: "approval_requested", origin_channel: "telegram", origin_sender: "maya", origin_conversation_id: null, assigned_maintainer: "Maya", branch_name: null, pull_request_url: null, failure_reason: null, created_at: "2026-08-06T10:00:00Z", updated_at: "2026-08-06T10:00:00Z", completed_at: null, repository: { id: "r1", name: "demo", owner: "octo", full_name: "octo/demo", github_url: "https://github.com/octo/demo", default_branch: "main", test_command: "pytest", lint_command: "ruff", protected_paths: [], coding_guidelines: null, autonomy_level: "approval_required", created_at: "2026-08-06T10:00:00Z", updated_at: "2026-08-06T10:00:00Z" }, events: [], approvals: [] }] }),
  channels: vi.fn().mockResolvedValue([{ id: "c1", channel_type: "slack", display_name: "Slack", status: "connected", configuration_summary: {}, last_event_at: null, created_at: "2026-08-06T10:00:00Z", updated_at: "2026-08-06T10:00:00Z" }]),
  decisions: vi.fn().mockResolvedValue([]),
} }));

describe("DashboardPage", () => {
  it("renders active task and approval metric", async () => {
    renderWithQuery(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("Add retry guidance")).toBeInTheDocument());
    expect(screen.getByText("Engineering work, under control.")).toBeInTheDocument();
    expect(screen.getAllByText("awaiting approval").length).toBeGreaterThan(0);
  });
});

