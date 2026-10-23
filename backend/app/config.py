from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    apify_token: SecretStr | None = Field(default=None, alias="APIFY_TOKEN")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")
    database_url: str = Field(default=f"sqlite:///{BACKEND_DIR / 'jobradar.db'}", alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    llm_model: str = Field(default="claude-sonnet-5-5", alias="LLM_MODEL")
    max_run_cost_usd: float = Field(default=5.0, alias="MAX_RUN_COST_USD")

    # Honour robots.txt before every verification fetch. Disallowed URLs are marked "uncertain".
    respect_robots_txt: bool = Field(default=True, alias="RESPECT_ROBOTS_TXT")
    # Opt into Anthropic's server-side refusal fallback (beta) for LLM calls.
    llm_fallbacks: bool = Field(default=True, alias="LLM_FALLBACKS")
    # Encrypts pooled Apify keys at rest. If unset, a key is generated into secret_key_file.
    secret_key: SecretStr | None = Field(default=None, alias="JOBRADAR_SECRET_KEY")
    secret_key_file: str = Field(default=str(BACKEND_DIR / ".secret_key"), alias="SECRET_KEY_FILE")
    # Calendar day boundary for daily Apify key rotation.
    key_rotation_tz: str = Field(default="Asia/Kolkata", alias="KEY_ROTATION_TZ")
    cors_origins: list[str] = Field(default=["http://localhost:5173"], alias="CORS_ORIGINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @model_validator(mode="before")
    @classmethod
    def _blank_is_unset(cls, data):
        """`KEY=` in .env means "use the default", not an empty value."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not (isinstance(v, str) and not v.strip())}
        return data

    @property
    def secrets(self) -> list[str]:
        out = []
        for s in (self.apify_token, self.anthropic_api_key, self.google_api_key, self.secret_key):
            if s and s.get_secret_value():
                out.append(s.get_secret_value())
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


ALLOWED_MODELS = ["claude-sonnet-5-5", "claude-opus-5-5"]
