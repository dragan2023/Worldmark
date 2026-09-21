"""管理员用户管理：列表、角色调整、封禁/解封、软删（封禁）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_admin
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import Membership
from app.models.user import User
from app.services.permissions import normalize_role, role_at_least

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])

_STATUSES = {"active", "banned"}


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=16)
    status: str | None = Field(default=None, min_length=1, max_length=16)


def _serialize(db: Session, user: User) -> dict[str, object]:
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "tier": membership.tier.value if membership is not None else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")
    return user


def _guard_self_action(operator: CurrentMember, target: User, changing: str) -> None:
    if operator.user_id != target.id:
        return
    if changing == "role":
        raise HTTPException(status_code=422, detail="不能修改自己的角色。")
    if changing == "status" and target.status == "active":
        raise HTTPException(status_code=422, detail="不能封禁自己的账号。")


@router.get("")
def list_users(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: CurrentMember = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    stmt = select(User).order_by(User.id.asc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.username.contains(q.strip()), User.email.contains(q.strip())))
    total = len(db.scalars(select(User.id)).all())
    users = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "items": [_serialize(db, user) for user in users]}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    operator: CurrentMember = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    user = _get_user(db, user_id)

    if payload.role is not None and payload.role != user.role:
        new_role = normalize_role(payload.role)
        # 只有更高（或同级）管理员能调整角色；且不能把比自己权限高的人降级
        if not role_at_least(operator.role, UserRole.ADMIN):
            raise HTTPException(status_code=403, detail="仅管理员可调整角色。")
        _guard_self_action(operator, user, "role")
        user.role = new_role

    if payload.status is not None and payload.status != user.status:
        if payload.status not in _STATUSES:
            raise HTTPException(status_code=422, detail="非法的状态值，仅支持 active / banned。")
        _guard_self_action(operator, user, "status")
        user.status = payload.status

    db.commit()
    db.refresh(user)
    return _serialize(db, user)


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: int,
    operator: CurrentMember = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """软删：封禁账号（保留贡献归属与审计线索）。"""
    user = _get_user(db, user_id)
    _guard_self_action(operator, user, "status")
    user.status = "banned"
    db.commit()
    return {"id": user.id, "status": user.status, "deleted": True}
