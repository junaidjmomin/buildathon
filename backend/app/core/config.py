from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    database_url: str = Field(default="", alias="DATABASE_URL")
    migration_database_url: str = Field(default="", alias="MIGRATION_DATABASE_URL")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE", ge=1, le=20)
    database_max_overflow: int = Field(default=5, alias="DATABASE_MAX_OVERFLOW", ge=0, le=20)
    database_disable_prepared_statements: bool = Field(
        default=True, alias="DATABASE_DISABLE_PREPARED_STATEMENTS"
    )

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(
        default="sl3dge-private", alias="SUPABASE_STORAGE_BUCKET"
    )

    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    llm_model: str = Field(default="openai/gpt-oss-120b", alias="LLM_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS"
    )

    @property
    def effective_migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
