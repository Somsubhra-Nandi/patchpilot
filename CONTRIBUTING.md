# Contributing to PatchPilot

PatchPilot optimizes for a focused, safe hackathon prototype.

1. Keep Caspian-specific code inside `apps/api/patchpilot/caspian`.
2. Add workflow transitions only through `WorkflowStateService`.
3. Add tests for every new command, approval rule, protected-path rule, or external API behavior.
4. Never add automatic merge, force-push, unrestricted shell execution, or secret-bearing API responses.
5. Mark simulated evidence explicitly.

Before opening a pull request:

```bash
make lint
make test
docker compose build
```

