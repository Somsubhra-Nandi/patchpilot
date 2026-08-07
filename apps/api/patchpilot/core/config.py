from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    app_secret_key: str = "change-me-for-production"
    database_url: str = "sqlite:///./patchpilot.sqlite3"
    frontend_url: str = "http://localhost:3000"
    api_public_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    auto_create_schema: bool = True
    seed_demo_data: bool = True

    github_token: str | None = None
    github_write_enabled: bool = False
    patchpilot_demo_mode: bool = True
    demo_repository_path: Path | None = None

    llm_provider: str = "deterministic"
    llm_api_key: str | None = None
    llm_model: str = "deterministic-planner-v1"

    caspian_enabled: bool = False
    caspian_api_key: str | None = None
    caspian_base_url: str = "https://api.trycaspianai.com"
    caspian_telegram_bot_token: str | None = None
    caspian_slack_mode: str = "quick"
    caspian_slack_display_name: str = "PatchPilot"
    caspian_slack_icon_url: str | None = None
    caspian_slack_client_id: str | None = None
    caspian_slack_client_secret: str | None = None
    caspian_slack_signing_secret: str | None = None
    caspian_slack_bot_token: str | None = None
    caspian_slack_app_token: str | None = None
    caspian_start_listener: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def effective_cors_origins(self) -> list[str]:
        return sorted(set([*self.cors_origins, self.frontend_url]))


@lru_cache
def get_settings() -> Settings:
    return Settings()
