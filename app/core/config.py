from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = "postgresql+psycopg://expenses:expenses@localhost:5432/expenses"
    environment: str = "development"
    session_lifetime_seconds: int = Field(default=604800, ge=300, le=2592000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
