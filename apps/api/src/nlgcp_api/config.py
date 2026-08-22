"""Environment-backed API configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Non-secret service settings."""

    model_config = SettingsConfigDict(env_prefix="NLGCP_", env_file=".env", extra="ignore")
    service_name: str = "nlgcp-api"


settings = Settings()
