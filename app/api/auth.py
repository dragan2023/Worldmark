"""认证 API：注册 / 登录 / 登出 / 当前用户。"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import rate_limit as login_rate_limit
from app.core.auth import (
    ACCESS_TOKEN_COOKIE,
    CurrentMember,
    create_access_token,
    get_current_member,
)
from app.core.config import get_settings
from app.core.password import hash_password, verify_password
from app.db.session import get_db
from app.models.enums import MembershipTier, UserStatus, UserRole
from app.models.membership import Membership
from app.models.user import User
from app.services.permissions import normalize_role, permissions_for_role

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_TOKEN_MAX_AGE_SECONDS = 8 * 3600


_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
        max_age=_TOKEN_MAX_AGE_SECONDS,
        path="/",
    )


def _user_payload(user: User, token: str | None = None) -> dict[str, object]:
    role = normalize_role(user.role)
    payload: dict[str, object] = {
        "authenticated": True,
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": role.value,
        "tier": user.membership.tier.value if user.membership else MembershipTier.FREE.value,
        "permissions": asdict(permissions_for_role(role)),
    }
    if token is not None:
        payload["token"] = token
    return payload


def _load_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(
        select(User).options(selectinload(User.membership)).where(User.username == username.strip().lower())
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    username = payload.username.strip().lower()
    email = payload.email.strip().lower()
    if not _USERNAME_PATTERN.match(username):
        raise HTTPException(status_code=422, detail="用户名需为 3-32 位英文、数字或下划线。")
    if not _EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="邮箱格式不正确。")
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已被占用，换一个试试。")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录。")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole.LEVEL2.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tier=MembershipTier.FREE, expires_at=None))
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    return _user_payload(user, token=token)


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    client_ip = request.client.host if request.client else "unknown"
    if login_rate_limit.is_blocked(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请 15 分钟后再试。",
            headers={"Retry-After": str(login_rate_limit.retry_after_seconds(client_ip))},
        )
    user = _load_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        login_rate_limit.register_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码不正确。")
    if user.status == UserStatus.BANNED.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该账号已被封禁，如有疑问请联系管理员。")

    login_rate_limit.reset(client_ip)

    user.last_login_at = datetime.now(UTC)
    if user.membership is None:
        db.add(Membership(user_id=user.id, tier=MembershipTier.FREE, expires_at=None))
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    return _user_payload(user, token=token)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(member: CurrentMember = Depends(get_current_member), db: Session = Depends(get_db)) -> dict[str, object]:
    if member.user_id is None:
        return {"authenticated": False, "role": "anonymous"}
    user = db.get(User, member.user_id)
    if user is None:
        return {"authenticated": False, "role": "anonymous"}
    return _user_payload(user)
