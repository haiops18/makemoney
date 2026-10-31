from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    owner_api_key: SecretStr = SecretStr("change-me")
    database_url: str = "postgresql+psycopg://auto_money:change-me@postgres:5432/auto_money"
    redis_url: str = "redis://redis:6379/0"
    monthly_budget_usd: int = 50
    budget_reserve_usd: int = 5
    timezone: str = "Asia/Ho_Chi_Minh"

    def validate_deployment(self) -> None:
        if self.environment == "production" and self.owner_api_key.get_secret_value() in {"change-me", "replace-with-a-long-random-secret"}:
            raise RuntimeError("OWNER_API_KEY must be configured in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()

