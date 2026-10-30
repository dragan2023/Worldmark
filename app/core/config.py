from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.http_env import normalize_no_proxy

# 必须在任何 httpx 客户端创建前执行：NO_PROXY 里的 [::1] 会让 httpx 直接抛 InvalidURL。
normalize_no_proxy()

# 已知示例/开发默认密钥：生产环境必须拒绝，避免用公开可猜的密钥签发令牌。
INSECURE_SECRET_KEYS = frozenset(
    {
        "",
        "development-only-change-me-before-production",
        "change-me",
        "changeme",
        "secret",
        "your-secret-key",
        "test",
        "password",
    }
)
MIN_PRODUCTION_SECRET_LENGTH = 32


class InsecureConfigurationError(RuntimeError):
    """生产环境配置不合格。消息只写配置项名，绝不回显取值。"""


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    dev_bypass_auth: bool = False
    app_secret_key: SecretStr = SecretStr("development-only-change-me-before-production")
    database_url: str = "sqlite+pysqlite:///./ip_landmarks.db"
    map_tile_url: str | None = None
    amap_web_service_api_key: SecretStr | None = None
    meituan_ht_token: SecretStr | None = None
    meituan_travel_token: SecretStr | None = None
    search_provider: str = "deepseek_web_search"
    admin_api_token: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: bool = False
    route_optimizer_provider: str = "haversine"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def __init__(self, **values: object) -> None:
        super().__init__(**values)
        self._assert_production_ready()

    def _assert_production_ready(self) -> None:
        """生产环境拒绝空值、示例值和过短密钥。

        故意在 pydantic 校验之后单独抛错：pydantic 的 ValidationError 会把
        ``input_value`` 原样拼进消息，等于把密钥写进日志。这里只报配置项名。
        """
        if not self.is_production:
            return
        value = self.app_secret_key.get_secret_value().strip()
        if value.lower() in INSECURE_SECRET_KEYS or len(value) < MIN_PRODUCTION_SECRET_LENGTH:
            raise InsecureConfigurationError(
                "配置项 APP_SECRET_KEY 在生产环境不可使用默认值或过短密钥，"
                f"请配置至少 {MIN_PRODUCTION_SECRET_LENGTH} 位的随机值。"
            )
        if self.dev_bypass_auth:
            raise InsecureConfigurationError("配置项 DEV_BYPASS_AUTH 在生产环境必须关闭。")

    @property
    def effective_meituan_travel_token(self) -> SecretStr | None:
        """Use the official Skill token name while preserving local migration compatibility."""
        return self.meituan_ht_token or self.meituan_travel_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
