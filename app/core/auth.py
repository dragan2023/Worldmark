from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.enums import MembershipTier
from app.models.membership import Membership
from app.models.user import User
from app.services.entitlements import EntitlementService

DEV_USER_EMAIL = "dev@iplandmarks.local"
DEV_USER_PASSWORD_HASH = "dev-mode-no-login"

ACCESS_TOKEN_COOKIE = "ip_landmark_access_token"


@dataclass(frozen=True)
class CurrentMember:
    user_id: int | None
    tier: MembershipTier


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
        user = User(email=DEV_USER_EMAIL, password_hash=DEV_USER_PASSWORD_HASH)
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
            return CurrentMember(dev_user.id, dev_user.membership.tier)
        return CurrentMember(None, MembershipTier.FREE)
    try:
        payload = jwt.decode(token, settings.app_secret_key.get_secret_value(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        if settings.dev_bypass_auth and not settings.is_production:
            dev_user = _ensure_dev_user(db)
            return CurrentMember(dev_user.id, dev_user.membership.tier)
        return CurrentMember(None, MembershipTier.FREE)

    user = db.scalar(select(User).options(selectinload(User.membership)).where(User.id == user_id))
    if user is None or user.membership is None:
        if settings.dev_bypass_auth and not settings.is_production:
            dev_user = _ensure_dev_user(db)
            return CurrentMember(dev_user.id, dev_user.membership.tier)
        return CurrentMember(None, MembershipTier.FREE)
    expires_at = user.membership.expires_at
    if expires_at is not None and expires_at < datetime.now(UTC):
        return CurrentMember(user.id, MembershipTier.FREE)
    return CurrentMember(user.id, user.membership.tier)


def require_entitlement(feature: str):
    def dependency(member: CurrentMember = Depends(get_current_member)) -> CurrentMember:
        if not getattr(EntitlementService.for_tier(member.tier), feature, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "membership_required", "upgrade_url": "/membership", "feature": feature},
            )
        return member

    return dependency
