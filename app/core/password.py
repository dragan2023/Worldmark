"""密码哈希：PBKDF2-SHA256（标准库实现，无第三方依赖）。"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return _ALGORITHM + "$" + str(_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()


def verify_password(password: str, encoded: str | None) -> bool:
    """校验密码；非本格式的历史占位串（如 dev 用户）一律返回 False。"""
    if not encoded:
        return False
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = encoded.split("$")
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_raw)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False
