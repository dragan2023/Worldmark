"""用户密钥解析：普通用户只能用自配密钥；管理员未自配时可回落系统密钥。

解析结果以 `Settings` 副本的形式交付——各服务原本就从 settings 取密钥，
因此无需改动服务内部实现，只需在请求入口替换传入的 settings。
"""

from __future__ import annotations

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import secret_box
from app.core.config import Settings
from app.models.enums import UserRole
from app.models.user_api_key import UserApiKey
from app.services.permissions import normalize_role

# provider → 该 provider 在 Settings 中对应的密钥字段
PROVIDER_FIELDS: dict[str, tuple[str, ...]] = {
    "deepseek": ("deepseek_api_key",),
    "amap": ("amap_web_service_api_key",),
    "bocha": ("bocha_api_key",),
    "meituan": ("meituan_ht_token", "meituan_travel_token"),
}


class UserKeyRequired(Exception):
    """普通用户未自配密钥（不回落系统密钥）。"""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"未配置 {provider} 密钥：请到「个人密钥」页配置后再使用该功能。")


class KeyResolutionService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def user_key(self, user_id: int, provider: str) -> str | None:
        row = self._db.scalar(
            select(UserApiKey).where(
                UserApiKey.user_id == user_id,
                UserApiKey.provider == provider,
                UserApiKey.is_active.is_(True),
            )
        )
        if row is None:
            return None
        try:
            return secret_box.decrypt(row.encrypted_value)
        except ValueError:
            return None

    def set_key(self, user_id: int, provider: str, raw_value: str, verified: bool) -> UserApiKey:
        row = self._db.scalar(
            select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == provider)
        )
        encrypted = secret_box.encrypt(raw_value.strip())
        if row is None:
            row = UserApiKey(
                user_id=user_id,
                provider=provider,
                encrypted_value=encrypted,
                key_hint=secret_box.key_hint(raw_value),
            )
            self._db.add(row)
        else:
            row.encrypted_value = encrypted
            row.key_hint = secret_box.key_hint(raw_value)
            row.is_active = True
        from datetime import UTC, datetime

        row.verified_at = datetime.now(UTC) if verified else None
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete_key(self, user_id: int, provider: str) -> bool:
        row = self._db.scalar(
            select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == provider)
        )
        if row is None:
            return False
        self._db.delete(row)
        self._db.commit()
        return True

    def effective_settings(self, member, settings: Settings) -> Settings:
        """返回注入用户密钥后的 Settings 副本。

        - 未登录：原样返回（调用方应先用 require_member 拦截）
        - 普通用户：配置了用户密钥的 provider 用用户密钥，未配置的**清空**系统密钥
        - 管理员：未配置用户密钥的 provider 保留系统密钥（回落）
        """
        if member.user_id is None:
            return settings
        role = normalize_role(member.role)
        overrides: dict[str, SecretStr | None] = {}
        for provider, fields in PROVIDER_FIELDS.items():
            user_value = self.user_key(member.user_id, provider)
            if user_value:
                secret = SecretStr(user_value)
                for field in fields:
                    overrides[field] = secret
            elif role != UserRole.ADMIN:
                for field in fields:
                    overrides[field] = None
        if not overrides:
            return settings
        return settings.model_copy(update=overrides)
