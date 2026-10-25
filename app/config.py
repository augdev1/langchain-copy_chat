from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/copybot"
    REDIS_URL: str = "redis://localhost:6379/0"

    GEMINI_API_KEY: str = "mock-api-key"
    GEMINI_MODEL: str = "gemini-3.8-flash"

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Concurrency and Cache parameters
    REDIS_DEDUP_TTL_SECONDS: int = 300  # 5 minutes
    REDIS_LOCK_TIMEOUT_SECONDS: float = 10.0  # Distributed lock lease timeout
    REDIS_LOCK_BLOCKING_TIMEOUT_SECONDS: float = 2.0  # Max time to wait for lock
    REDIS_SESSION_CACHE_TTL_SECONDS: int = 1800  # 30 minutes

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str = "http://evolution:8080"
    EVOLUTION_API_KEY: str = "evolution_secret_key_123"
    EVOLUTION_INSTANCE_NAME: str = "copybot"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
