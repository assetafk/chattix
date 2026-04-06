from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://chattix:chattix@localhost:5432/chattix"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 10
    presence_ttl_seconds: int = 90
    typing_ttl_seconds: int = 6


def get_settings() -> Settings:
    return Settings()
