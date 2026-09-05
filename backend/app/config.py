from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    redis_url: str

    dataset_seed: int = 42
    outcome_seed: int = 2026
    dataset_size: int = 300
    development_percent: int = 80

    openai_api_key: str | None = None
    openai_enabled: bool = False
    openai_primary_model: str = "gpt-5.6-terra"
    openai_escalation_model: str = "gpt-5.6-sol"
    openai_realtime_model: str = "gpt-realtime-2.1"
    openai_realtime_voice: str = "marin"

    groq_api_key: str | None = None
    groq_enabled: bool = False
    groq_primary_model: str = "openai/gpt-oss-20b"
    groq_escalation_model: str = "openai/gpt-oss-120b"
    groq_stt_model: str = "whisper-large-v3-turbo"
    groq_tts_model: str = "canopylabs/orpheus-v1-english"
    groq_tts_voice: str = "hannah"
    voice_ai_provider: str = "groq"

    high_value_threshold_paise: int = 1_000_000
    quiet_hours_start: int = 21
    quiet_hours_end: int = 9
    contact_cooldown_hours: int = 12
    max_retries: int = 3
    max_reminders: int = 2
    max_voice_calls: int = 1
    max_automatic_discount_paise: int = 50_000

    public_api_url: str = "https://your-public-domain.example"
    public_ws_url: str = "wss://your-public-domain.example"
    frontend_url: str = "http://localhost:3000"
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_voice_from: str | None = None
    twilio_human_transfer_number: str | None = None
    twilio_fallback_audio_url: str | None = None

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_settings() -> Settings:
    return settings
