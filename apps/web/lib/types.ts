export type Repository = {
  id: string;
  name: string;
  owner: string;
  full_name: string;
  github_url: string;
  default_branch: string;
  test_command: string | null;
  lint_command: string | null;
  protected_paths: string[];
  coding_guidelines: string | null;
  autonomy_level: string;
  created_at: string;
  updated_at: string;
};

export type ValidationResult = {
  command: string;
  exit_code: number;
  duration_ms: number;
  output_summary: string;
  simulated: boolean;
};

export type PullRequestPayload = {
  title: string;
  head: string;
  base: string;
  body: string;
  draft: boolean;
  issue: string;
};

export type PatchArtifact = { changed_files?: string[] };

export type EventDetails = {
  [key: string]: unknown;
  plan?: Plan;
  results?: ValidationResult[];
  simulated?: boolean;
  mode?: string;
  error?: unknown;
  pull_request?: PullRequestPayload;
  artifact?: PatchArtifact;
};

export type TaskEvent = {
  id: string;
  task_id: string;
  event_type: string;
  stage: string;
  summary: string;
  details: EventDetails;
  channel: string | null;
  actor: string | null;
  created_at: string;
};

export type Approval = {
  id: string;
  approval_type: string;
  status: string;
  requested_channel: string;
  requested_from: string | null;
  responded_channel: string | null;
  responded_by: string | null;
  response_note: string | null;
  created_at: string;
  responded_at: string | null;
};

export type Decision = {
  id: string; task_id: string; decision_type: string; title: string;
  context: { relevant_files?: string[]; [key: string]: unknown };
  risk_level: string; options: { id: string; label: string; risk?: string }[];
  recommended_option: string | null; requested_by_agent: string; status: string;
  created_at: string; resolved_at: string | null; resolved_by: string | null;
  resolved_channel: string | null; resolution: string | null; resolution_note: string | null;
};

export type Task = {
  id: string;
  repository_id: string;
  github_issue_number: number;
  github_issue_url: string;
  title: string;
  description: string | null;
  status: string;
  current_stage: string;
  origin_channel: string;
  origin_sender: string;
  origin_conversation_id: string | null;
  assigned_maintainer: string | null;
  branch_name: string | null;
  pull_request_url: string | null;
  failure_reason: string | null;
  coding_agent_provider: string | null;
  external_session_id: string | null;
  agent_execution_status: string | null;
  last_checkpoint: Record<string, unknown>;
  last_execution_at: string | null;
  workspace_path: string | null;
  workspace_status: string | null;
  source_commit_sha: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  repository: Repository;
  events: TaskEvent[];
  approvals: Approval[];
  decisions: Decision[];
};

export type TaskList = { items: Task[]; total: number; page: number; page_size: number };

export type Channel = {
  id: string;
  channel_type: string;
  display_name: string;
  status: string;
  configuration_summary: Record<string, unknown>;
  last_event_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Plan = {
  issue_summary: string;
  suspected_change: string;
  relevant_files: string[];
  proposed_modifications: string[];
  validation_strategy: string[];
  risks: string[];
  open_questions: string[];
  confidence: string;
};
