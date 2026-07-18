"""
Purpose of this file.
Centralized application configuration loaded from environment variables.
Responsibility of this file.
Validating required env vars exist at startup, and being the single import point for config across the service.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    ms_client_id: str
    ms_client_secret: str
    ms_tenant_id: str = "common"
    ms_redirect_uri: str
    ms_scopes: str = "offline_access Mail.Send Mail.Read User.Read"

    token_encryption_key: str
    n8n_service_api_key: str
    n8n_webhook_url: str = "http://localhost:5678/webhook/customer-import"
    n8n_engagement_webhook_url: str = "http://localhost:5678/webhook/engagement-run"
    oauth_state_secret: str

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    environment: str = "production"
    log_level: str = "INFO"
    app_port: int = 8000
    allowed_origins: str = "*"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def ms_scopes_list(self) -> list[str]:
        return self.ms_scopes.split()

    @property
    def ms_authorize_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.ms_tenant_id}/oauth2/v2.0/authorize"

    @property
    def ms_token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.ms_tenant_id}/oauth2/v2.0/token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
