# PatchPilot five-minute judging demo

## Before the call

1. Run `cp .env.example .env` and `docker compose up --build`.
2. Open `http://localhost:3000/dashboard` and `http://localhost:8000/docs` in separate tabs.
3. If demonstrating real channels, complete [caspian-setup.md](caspian-setup.md), send `/patchpilot help` to both bots, and keep Slack plus Telegram visible.
4. Keep `GITHUB_WRITE_ENABLED=false` unless using a repository and token created specifically for the demo.
5. Verify both health checks and that the dashboard shows the three seeded missions.

## 0:00–0:35 — Position the product

Show the dashboard.

Say: “PatchPilot is not another coding chat. It is a controlled maintainer workflow. Assign an issue from Slack, approve the plan from Telegram, and receive a tested draft PR on GitHub.”

Point out active missions, waiting approvals, completed/failed outcomes, connected channels, and audit activity. Emphasize that no metric is fabricated; these counts come from persisted tasks.

## 0:35–1:05 — Start from Slack

In Slack, send:

```text
/patchpilot start <your-public-owner>/<your-demo-repo>#<issue-number>
```

For a credential-free fallback, run `make demo`, copy the printed task ID, and immediately open `http://localhost:3000/tasks/<task-id>`.

Say: “Slack and Telegram are not separate bots in our code. Caspian normalizes both into this one handler.”

## 1:05–2:00 — Show analysis and plan

Open the new task page. Walk down the execution path and live audit timeline:

- Message received.
- Issue loaded.
- Repository map built.
- Relevant files ranked by deterministic heuristics.
- Structured implementation plan generated.
- Approval requested.

Open the plan section and show issue assessment, suspected change, relevant files, modifications, validation strategy, risk, and confidence.

Say: “At this point write operations are physically blocked by the task state. Planning is not permission.”

## 2:00–2:35 — Approve from Telegram

Copy the task ID and send in Telegram:

```text
/patchpilot approve <task-id>
```

Say: “The task began in Slack but approval can come from Telegram. PatchPilot records both identities and both channels against one approval.”

Point at the approval gate changing and the audit event identifying Telegram.

## 2:35–3:35 — Watch safe execution

Show the timeline update via SSE:

- Branch prepared.
- Safe patch generated.
- Protected paths checked.
- Validation run or simulated.
- Draft PR payload prepared.

Point out every “simulated” badge if running without a checkout or GitHub write credentials.

Say: “We never imply a simulated effect is real. In write mode the same approval can create a new branch and draft PR, but it still cannot merge or force-push.”

## 3:35–4:15 — Show validation evidence and PR

Open “Proposed change & validation.” Show command, exit code, duration, output summary, and whether the result is simulated.

Open “Draft pull request.” Show title, base/head, issue reference, changes, validation, risk, approval attribution, and PatchPilot attribution.

If using live write mode, click “Open on GitHub” and show the PR is a draft.

## 4:15–4:40 — Cross-channel completion

Show the final Slack and Telegram messages. Then show “Channel activity” and the final audit events.

Say: “Caspian lets PatchPilot choose the right existing conversation for each update while our product logic stays channel-independent.”

## 4:40–5:00 — Close on trust

Show repository settings: validation commands, protected paths, coding guidelines, autonomy. Then show channel settings without secrets.

Close with: “PatchPilot’s differentiator is controlled continuity. The human keeps authority; the agent keeps context and evidence across every channel.”

## Backup paths

- Caspian credentials unavailable: use `make demo`; the UI and safe workflow remain complete.
- GitHub rate limit or private issue: use the seeded demo repository/task.
- Real tests too slow: unset `DEMO_REPOSITORY_PATH` to show clearly labeled simulated validation.
- A validation fails: use the seeded failed task to demonstrate safe stop and failure evidence.
- Network drops: show the completed seeded task and explain the same persisted event model.

