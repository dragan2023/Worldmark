from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    dev_bypass_auth: bool = True
    app_secret_key: SecretStr = SecretStr("development-only-change-me-before-production")
    database_url: str = "sqlite+pysqlite:///./ip_landmarks.db"
    map_tile_url: str | None = None
    amap_web_service_api_key: SecretStr | None = None
    meituan_ht_token: SecretStr | None = None
    meituan_travel_token: SecretStr | None = None
    search_provider: str = "bocha_web_search"
    bocha_api_key: SecretStr | None = None
    admin_api_token: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: bool = False
    route_optimizer_provider: str = "haversine"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def effective_meituan_travel_token(self) -> SecretStr | None:
        """Use the official Skill token name while preserving local migration compatibility."""
        return self.meituan_ht_token or self.meituan_travel_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
