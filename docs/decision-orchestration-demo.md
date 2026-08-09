# Human interruption demo

1. Start the stack with `docker compose up -d --build` and confirm Slack and Telegram are connected through the existing Caspian configuration.
2. From Slack, send `patchpilot start owner/repo#42`. For a deterministic escalation without changing GitHub, create/use an issue whose title or body contains `strategy`.
3. PatchPilot records the fake-agent session, moves the task to `waiting_for_human`, creates a decision, and broadcasts the question through the configured gateways.
4. From Telegram, send `patchpilot decisions`, then `patchpilot explain <decision-id>`.
5. Resolve the compatibility scenario with `patchpilot choose <decision-id> B`.
6. Confirm the same task/session resumes, validation completes, both configured channels receive the final update, and the task page shows the request, Telegram resolution, resume, validation, and completion events.

Useful API equivalents:

- `GET /api/decisions?status=pending`
- `POST /api/decisions/{id}/resolve` with `{"option":"B","actor":"demo-maintainer","channel":"telegram"}`
- `POST /api/tasks/{id}/pause`
- `POST /api/tasks/{id}/resume`

The adapter is deliberately deterministic and does not write repository changes. GitHub write mode retains its existing opt-in draft-only safeguards.
