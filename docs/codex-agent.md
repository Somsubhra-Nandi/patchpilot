# Codex coding agent

PatchPilot integrates Codex through the official `@openai/codex` CLI in non-interactive `codex exec --json` mode. Initial calls use `--output-schema` and the adapter maps the JSONL `thread.started` and final `agent_message` events into the existing Pydantic agent models. Continuations use `codex exec ... resume <session-id>` with a structured output schema. The Codex home directory is persisted in a dedicated Docker volume so login and session records survive API container recreation.

PatchPilot remains authoritative for workspace creation, task branches, policy evaluation, decisions, validation evidence, audit events, Caspian messages, and GitHub write guards. Codex receives no communication-channel responsibility and runs with `read-only` during analysis and `workspace-write` during implementation.

## First real demo

1. Set `CODING_AGENT_PROVIDER=codex`, `PATCHPILOT_DEMO_MODE=false`, and keep `GITHUB_WRITE_ENABLED=false` for the first run.
2. Build the image: `docker compose up -d --build`.
3. Authenticate the dedicated Codex volume: `docker compose exec api codex login`.
4. Confirm authentication: `docker compose exec api codex login status`.
5. Optionally verify isolation with `docker compose exec api python -m patchpilot.codex_smoke`. The smoke test creates only a temporary local repository and follows `AGENT_WORKSPACE_RETAIN`.
6. From Slack, send `patchpilot start owner/repo#42`.
7. Approve from Telegram with `patchpilot approve <task-id>`.
8. Resolve later interruptions with `patchpilot decisions`, `patchpilot explain <decision-id>`, and `patchpilot choose <decision-id> <option>`.

For a credential-free demo, leave `CODING_AGENT_PROVIDER=fake`.

## Continuity and retention

The database stores the Codex thread ID, workspace path, source SHA, agent checkpoint, and branch. `/root/.codex` and `/workspaces` use separate named Docker volumes. A new adapter instance restores the thread-to-workspace association and resumes the official Codex session. If the CLI session record is unavailable, the adapter fails explicitly; it does not pretend that a new session is the old one.

Set `AGENT_WORKSPACE_RETAIN=false` to remove completed task workspaces. Cleanup validates that the target is a direct child of the configured workspace root before deletion.

## Current GitHub write behavior

Safe mode preserves the complete local Codex diff and prepares a draft-PR payload without pushing. The existing guarded write mode still creates a new task branch and draft PR through the GitHub API, never force-pushes, never updates the default branch, and never merges. Its current remote artifact is the PatchPilot proposal document; publishing the complete local Git tree through the GitHub Git Data API remains a deliberate follow-up before enabling real-diff write mode in production.
