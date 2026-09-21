"""用户密钥静态加密：Fernet（AES-CBC + HMAC），密钥由 APP_SECRET_KEY 派生。"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_DERIVE_SALT = b"worldmark-user-api-key-box"
_ITERATIONS = 100_000
_box: Fernet | None = None


def _get_box() -> Fernet:
    global _box
    if _box is None:
        master = get_settings().app_secret_key.get_secret_value().encode("utf-8")
        derived = hashlib.pbkdf2_hmac("sha256", master, _DERIVE_SALT, _ITERATIONS)
        _box = Fernet(base64.urlsafe_b64encode(derived))
    return _box


def encrypt(value: str) -> str:
    return _get_box().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _get_box().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:  # APP_SECRET_KEY 变更或数据损坏
        raise ValueError("密钥解密失败：请重新保存你的密钥。") from exc


def key_hint(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]
