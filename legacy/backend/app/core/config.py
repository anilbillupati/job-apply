from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Job Apply API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./job_apply.db"
    cors_origins: List[str] = ["http://localhost:5173"]
    request_timeout_seconds: float = 20.0
    user_agent: str = "Mozilla/5.0 (compatible; JobApplyBot/0.1)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
