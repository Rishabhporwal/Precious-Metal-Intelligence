from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Quant engine configuration. Read once at startup; no business logic here."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"
    port: int = 8001
    log_level: str = "info"
    database_url: str | None = None
    redis_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
