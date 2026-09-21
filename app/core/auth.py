from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import secrets

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.enums import MembershipTier, UserStatus, UserRole
from app.models.membership import Membership
from app.models.user import User
from app.services.entitlements import EntitlementService
from app.services.permissions import normalize_role, role_at_least

DEV_USER_EMAIL = "dev@iplandmarks.local"
DEV_USER_PASSWORD_HASH = "dev-mode-no-login"

ACCESS_TOKEN_COOKIE = "ip_landmark_access_token"


@dataclass(frozen=True)
class CurrentMember:
    user_id: int | None
    tier: MembershipTier
    role: UserRole


def create_access_token(user_id: int, settings: Settings | None = None, lifetime: timedelta = timedelta(hours=8)) -> str:
    configuration = settings or get_settings()
    return jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + lifetime},
        configuration.app_secret_key.get_secret_value(),
        algorithm="HS256",
    )


def _ensure_dev_user(db: Session) -> User:
    """Return or create the default development user with PREMIUM membership."""
    user = db.scalar(select(User).options(selectinload(User.membership)).where(User.email == DEV_USER_EMAIL))
    if user is None:
        user = User(username="dev", email=DEV_USER_EMAIL, password_hash=DEV_USER_PASSWORD_HASH, role=UserRole.ADMIN.value)
        db.add(user)
        db.flush()
        membership = Membership(user_id=user.id, tier=MembershipTier.PREMIUM, expires_at=None)
        db.add(membership)
        db.commit()
        db.refresh(user)
        user = db.scalar(select(User).options(selectinload(User.membership)).where(User.email == DEV_USER_EMAIL))
    if user.membership is None:
        membership = Membership(user_id=user.id, tier=MembershipTier.PREMIUM, expires_at=None)
        db.add(membership)
        db.commit()
        db.refresh(user)
    if not getattr(user, "username", None):  # 存量库回填
        user.username = "dev"
        db.commit()
        db.refresh(user)
    return user


ANONYMOUS_USER_EMAIL = "anonymous@iplandmarks.local"
ANONYMOUS_USER_PASSWORD_HASH = "anonymous-no-login"


def resolve_user_id(db: Session, member: CurrentMember) -> int:
    """Return the member's user id, creating a shared guest identity for anonymous visitors."""
    if member.user_id is not None:
        return member.user_id
    user = db.scalar(select(User).where(User.email == ANONYMOUS_USER_EMAIL))
    if user is None:
        user = User(email=ANONYMOUS_USER_EMAIL, password_hash=ANONYMOUS_USER_PASSWORD_HASH)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.id


def get_current_member(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentMember:
    token = access_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        if settings.dev_bypass_auth and not settings.is_production:
            dev_user = _ensure_dev_user(db)
            return CurrentMember(dev_user.id, dev_user.membership.tier, normalize_role(dev_user.role))
        return CurrentMember(None, MembershipTier.FREE, UserRole.LEVEL2)
    try:
        payload = jwt.decode(token, settings.app_secret_key.get_secret_value(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        if settings.dev_bypass_auth and not settings.is_production:
            dev_user = _ensure_dev_user(db)
            return CurrentMember(dev_user.id, dev_user.membership.tier, normalize_role(dev_user.role))
        return CurrentMember(None, MembershipTier.FREE, UserRole.LEVEL2)

    user = db.scalar(select(User).options(selectinload(User.membership)).where(User.id == user_id))
    if user is None or user.membership is None:
        if settings.dev_bypass_auth and not settings.is_production:
            dev_user = _ensure_dev_user(db)
            return CurrentMember(dev_user.id, dev_user.membership.tier, normalize_role(dev_user.role))
        return CurrentMember(None, MembershipTier.FREE, UserRole.LEVEL2)
    if user.status == UserStatus.BANNED.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该账号已被封禁，如有疑问请联系管理员。")
    role = normalize_role(user.role)
    if user.is_admin:
        role = UserRole.ADMIN
    expires_at = user.membership.expires_at
    if expires_at is not None and expires_at < datetime.now(UTC):
        return CurrentMember(user.id, MembershipTier.FREE, role)
    return CurrentMember(user.id, user.membership.tier, role)


def require_entitlement(feature: str):
    def dependency(member: CurrentMember = Depends(get_current_member)) -> CurrentMember:
        if not getattr(EntitlementService.for_tier(member.tier), feature, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "membership_required", "upgrade_url": "/membership", "feature": feature},
            )
        return member

    return dependency


def require_member(member: CurrentMember = Depends(get_current_member)) -> CurrentMember:
    """要求已登录会员；开发环境 dev_bypass_auth 自动以本地开发者身份通过。"""
    if member.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录后再执行该操作。")
    return member


def require_role(minimum: str | UserRole):
    """要求登录且角色不低于 minimum（level2 < level1 < admin）。"""

    def dependency(member: CurrentMember = Depends(get_current_member)) -> CurrentMember:
        if member.user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录后再执行该操作。")
        if not role_at_least(member.role, minimum):
            required = normalize_role(minimum)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "role_required", "required": required.value, "current": member.role.value},
            )
        return member

    return dependency


def require_admin(
    x_admin_token: str | None = Header(default=None),
    member: CurrentMember = Depends(get_current_member),
    settings: Settings = Depends(get_settings),
) -> CurrentMember:
    """管理员守卫：admin 角色用户，或过渡期兼容旧 X-Admin-Token（后续下线）。"""
    if member.user_id is not None and member.role == UserRole.ADMIN:
        return member
    configured_token = settings.admin_api_token.get_secret_value() if settings.admin_api_token else None
    if configured_token and x_admin_token and secrets.compare_digest(x_admin_token, configured_token):
        return member
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要管理员权限。")
