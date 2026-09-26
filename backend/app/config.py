"""Settings, read from environment variables or the .env file.

Pydantic checks the types for you: if ENABLE_SCHEDULER=maybe, the app refuses
to start instead of misbehaving later.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://footiq:footiq@localhost:5432/footiq"
    models_dir: Path = Path("../ml/models")

    data_provider: str = "api_football"
    api_football_key: str = ""
    football_data_org_key: str = ""

    enable_scheduler: bool = False
    scheduler_hour: int = 6
    timezone: str = "Asia/Kathmandu"

    jwt_secret: str = "change-me"
    access_token_minutes: int = 60 * 24 * 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
