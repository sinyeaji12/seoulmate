from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS = {"openai": "gpt-5-mini", "anthropic": "claude-sonnet-5-5"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    llm_provider: Literal["openai", "anthropic"] = "anthropic"
    model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_workspace_id: str = ""
    seoul_api_key: str = ""
    tour_api_key: str = ""
    seoulmate_mock_tools: bool = True
    max_tool_rounds: int = 6
    max_message_chars: int = 500

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.llm_provider]


def get_settings() -> Settings:
    return Settings()
