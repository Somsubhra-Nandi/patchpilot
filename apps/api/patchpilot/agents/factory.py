from patchpilot.agents.codex import CodexCodingAgent
from patchpilot.agents.coding import CodingAgent, FakeCodingAgent
from patchpilot.core.config import Settings


def create_coding_agent(settings: Settings) -> CodingAgent:
    if settings.coding_agent_provider == "fake":
        return FakeCodingAgent()
    if settings.coding_agent_provider == "codex":
        return CodexCodingAgent(executable=settings.codex_cli_path, model=settings.codex_model, timeout=settings.codex_timeout_seconds)
    raise ValueError(f"Unsupported coding agent provider: {settings.coding_agent_provider}")
