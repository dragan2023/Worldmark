"""生产配置守卫：默认/空/过短密钥必须启动失败，且错误信息不回显密钥。"""

from __future__ import annotations

import pytest

from app.core.config import InsecureConfigurationError, Settings


def _production(**overrides) -> Settings:
    values = {"app_env": "production", "dev_bypass_auth": False}
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "   ",
        "development-only-change-me-before-production",
        "change-me",
        "changeme",
        "short-secret",
    ],
)
def test_production_rejects_known_or_short_secret(secret):
    with pytest.raises(InsecureConfigurationError) as error:
        _production(app_secret_key=secret)
    message = str(error.value)
    assert "APP_SECRET_KEY" in message
    if secret.strip():
        assert secret.strip() not in message  # 不回显密钥内容


def test_production_accepts_long_random_secret():
    settings = _production(app_secret_key="a" * 48)
    assert settings.is_production is True


def test_production_rejects_dev_bypass():
    with pytest.raises(InsecureConfigurationError) as error:
        _production(app_secret_key="a" * 48, dev_bypass_auth=True)
    assert "DEV_BYPASS_AUTH" in str(error.value)


def test_development_keeps_local_defaults():
    settings = Settings(app_env="development")
    assert settings.is_production is False
    assert settings.app_secret_key.get_secret_value()
