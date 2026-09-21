"""创建/重置管理员账号。

用法：
    .venv/Scripts/python.exe scripts/create_admin.py <用户名> <密码> [邮箱]

- 用户名：3-32 位英文/数字/下划线，作为登录标识
- 已存在同名用户：重置其密码并提升为管理员（幂等）
- 未提供邮箱时默认 <用户名>@iplandmarks.local
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.password import hash_password, verify_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import MembershipTier, UserStatus, UserRole  # noqa: E402
from app.models.membership import Membership  # noqa: E402
from app.models.user import User  # noqa: E402

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    username = sys.argv[1].strip().lower()
    password = sys.argv[2]
    email = (sys.argv[3] if len(sys.argv) > 3 else f"{username}@iplandmarks.local").strip().lower()

    if not _USERNAME_PATTERN.match(username):
        print("用户名需为 3-32 位英文、数字或下划线。")
        sys.exit(1)
    if len(password) < 8:
        print("密码至少 8 位。")
        sys.exit(1)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        created = user is None
        if created:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN.value,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            db.flush()
        user.role = UserRole.ADMIN.value
        user.status = UserStatus.ACTIVE.value
        user.password_hash = hash_password(password)
        if user.email != email and db.scalar(select(User.id).where(User.email == email, User.id != user.id)) is None:
            user.email = email
        if user.membership is None:
            db.add(Membership(user_id=user.id, tier=MembershipTier.FREE, expires_at=None))
        db.commit()

        saved = db.scalar(select(User).where(User.username == username))
        assert verify_password(password, saved.password_hash)
        print(f"{'创建' if created else '重置'}管理员成功：username={saved.username} email={saved.email} role={saved.role}")


if __name__ == "__main__":
    main()
