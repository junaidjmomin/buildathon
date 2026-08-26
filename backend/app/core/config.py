from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    environment: Literal["development", "test", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    database_url: str = Field(default="", alias="DATABASE_URL")
    migration_database_url: str = Field(default="", alias="MIGRATION_DATABASE_URL")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE", ge=1, le=20)
    database_max_overflow: int = Field(default=5, alias="DATABASE_MAX_OVERFLOW", ge=0, le=20)
    database_disable_prepared_statements: bool = Field(
        default=True, alias="DATABASE_DISABLE_PREPARED_STATEMENTS"
    )

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: SecretStr = Field(
        default=SecretStr(""), alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_storage_bucket: str = Field(
        default="sl3dge-private", alias="SUPABASE_STORAGE_BUCKET"
    )

    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    llm_model: str = Field(default="openai/gpt-oss-120b", alias="LLM_MODEL")
    groq_api_key: SecretStr = Field(default=SecretStr(""), alias="GROQ_API_KEY")
    llm_timeout_seconds: int = Field(default=30, alias="LLM_TIMEOUT_SECONDS", ge=5, le=120)
    llm_max_output_tokens: int = Field(
        default=1200, alias="LLM_MAX_OUTPUT_TOKENS", ge=128, le=4096
    )
    llm_max_input_chars: int = Field(
        default=24000, alias="LLM_MAX_INPUT_CHARS", ge=2000, le=100000
    )
    agent_max_attempts: int = Field(default=2, alias="AGENT_MAX_ATTEMPTS", ge=1, le=5)
    agent_checkpoint_database_url: SecretStr = Field(
        default=SecretStr(""), alias="AGENT_CHECKPOINT_DATABASE_URL"
    )

    razorpay_key_id: SecretStr = Field(default=SecretStr(""), alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: SecretStr = Field(
        default=SecretStr(""), alias="RAZORPAY_KEY_SECRET"
    )
    razorpay_api_base_url: str = Field(
        default="https://api.razorpay.com/v1", alias="RAZORPAY_API_BASE_URL"
    )
    razorpay_mode: Literal["test", "live"] = Field(default="test", alias="RAZORPAY_MODE")
    razorpay_timeout_seconds: int = Field(
        default=20, alias="RAZORPAY_TIMEOUT_SECONDS", ge=3, le=60
    )
    razorpay_max_retries: int = Field(default=3, alias="RAZORPAY_MAX_RETRIES", ge=0, le=5)
    razorpay_max_pages: int = Field(default=100, alias="RAZORPAY_MAX_PAGES", ge=1, le=1000)
    razorpay_max_records: int = Field(
        default=100000, alias="RAZORPAY_MAX_RECORDS", ge=1, le=1000000
    )
    razorpay_max_response_bytes: int = Field(
        default=10 * 1024 * 1024,
        alias="RAZORPAY_MAX_RESPONSE_BYTES",
        ge=1024,
        le=50 * 1024 * 1024,
    )
    worker_tenant_ids: str = Field(default="novacart_demo", alias="WORKER_TENANT_IDS")
    worker_lease_seconds: int = Field(
        default=900, alias="WORKER_LEASE_SECONDS", ge=60, le=3600
    )
    worker_poll_seconds: int = Field(default=2, alias="WORKER_POLL_SECONDS", ge=1, le=30)

    @property
    def parsed_worker_tenant_ids(self) -> list[str]:
        return [item.strip() for item in self.worker_tenant_ids.split(",") if item.strip()]

    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS"
    )
    trusted_hosts: str = Field(
        default="localhost,127.0.0.1,testserver", alias="TRUSTED_HOSTS"
    )
    force_https: bool = Field(default=False, alias="FORCE_HTTPS")
    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024, alias="MAX_UPLOAD_BYTES", ge=1024, le=100 * 1024 * 1024
    )

    auth_mode: Literal["disabled", "oidc"] = Field(default="disabled", alias="AUTH_MODE")
    oidc_issuer: str = Field(default="", alias="OIDC_ISSUER")
    oidc_audience: str = Field(default="", alias="OIDC_AUDIENCE")
    oidc_jwks_url: str = Field(default="", alias="OIDC_JWKS_URL")
    oidc_tenant_claim: str = Field(default="merchant_id", alias="OIDC_TENANT_CLAIM")
    oidc_roles_claim: str = Field(default="roles", alias="OIDC_ROLES_CLAIM")

    @property
    def effective_migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def parsed_trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    def validate_runtime(self) -> None:
        if self.environment != "production":
            return
        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.migration_database_url or self.migration_database_url == self.database_url:
            missing.append("a distinct MIGRATION_DATABASE_URL")
        if not any(
            value in self.database_url for value in ("sslmode=require", "sslmode=verify-full")
        ):
            missing.append("PostgreSQL TLS with sslmode=require or verify-full")
        if not self.supabase_url or not self.supabase_service_role_key.get_secret_value():
            missing.append("Supabase Storage credentials")
        if not self.supabase_url.startswith("https://"):
            missing.append("HTTPS SUPABASE_URL")
        if self.auth_mode != "oidc":
            missing.append("AUTH_MODE=oidc")
        if not self.oidc_issuer or not self.oidc_audience or not self.oidc_jwks_url:
            missing.append("OIDC issuer, audience and JWKS URL")
        if any(
            origin == "*" or origin.startswith("http://")
            for origin in self.parsed_cors_origins
        ):
            missing.append("HTTPS-only explicit CORS_ORIGINS")
        if not self.force_https:
            missing.append("FORCE_HTTPS=true")
        checkpoint_url = self.agent_checkpoint_database_url.get_secret_value()
        if not checkpoint_url:
            missing.append("AGENT_CHECKPOINT_DATABASE_URL")
        elif not any(
            value in checkpoint_url for value in ("sslmode=require", "sslmode=verify-full")
        ):
            missing.append("LangGraph checkpoint PostgreSQL TLS")
        if self.razorpay_api_base_url != "https://api.razorpay.com/v1":
            missing.append("the approved Razorpay HTTPS API origin")
        if not self.parsed_worker_tenant_ids:
            missing.append("at least one WORKER_TENANT_IDS entry")
        if missing:
            raise RuntimeError(
                "Production configuration is unsafe or incomplete: " + "; ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
