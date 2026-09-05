from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_path: str = "vasooli.db"
    openai_api_key: str | None = None
    openai_enabled: bool = False
    openai_primary_model: str = "gpt-5.6-terra"
    openai_escalation_model: str = "gpt-5.6-sol"
    high_value_threshold_paise: int = 1_000_000
    quiet_hours_start: int = 21
    quiet_hours_end: int = 9
    contact_cooldown_hours: int = 12
    max_retries: int = 3
    max_reminders: int = 2
    max_voice_calls: int = 1
    max_automatic_discount_paise: int = 50_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
