from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    LLM_PROVIDER: str = "ollama"
    LLM_SMART_MODEL: str = "llama3.3"
    LLM_FAST_MODEL: str = "llama3.2"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://messageos:messageos@postgres:5432/messageos"
    DATABASE_URL_SYNC: str = "postgresql://messageos:messageos@postgres:5432/messageos"
    REDIS_URL: str = "redis://redis:6379"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""   # your personal chat ID with the bot
    DIGEST_TIMES: str = "08:00,12:30,19:00"

    # Gmail
    GMAIL_CREDENTIALS_FILE: str = "credentials/gmail_credentials.json"
    GMAIL_WORK_TOKEN_FILE: str = "credentials/gmail_work_token.json"
    GMAIL_PERSONAL_TOKEN_FILE: str = "credentials/gmail_personal_token.json"
    GMAIL_WORK_ADDRESS: str = ""
    GMAIL_PERSONAL_ADDRESS: str = ""
    GMAIL_PUBSUB_TOPIC: str = ""

    # Calendar
    GOOGLE_CALENDAR_ID: str = "primary"
    MEETING_SLOT_COUNT: int = 3
    MEETING_LOOKAHEAD_DAYS: int = 7

    # Search
    TAVILY_API_KEY: Optional[str] = None

    # Webhook
    WEBHOOK_BASE_URL: str = "http://localhost:8000"

    @property
    def digest_times_list(self) -> list[str]:
        return [t.strip() for t in self.DIGEST_TIMES.split(",")]


settings = Settings()
