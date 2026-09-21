"""角色权限矩阵：用户系统权限的唯一事实源。

两个维度相互独立：
- `UserRole`（本模块）：权限角色（admin > level1 > level2）
- `MembershipTier`（`entitlements.py`）：付费会员层，保留现状
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.models.enums import UserRole

_ROLE_ORDER: dict[UserRole, int] = {
    UserRole.LEVEL2: 0,
    UserRole.LEVEL1: 1,
    UserRole.ADMIN: 2,
}


@dataclass(frozen=True)
class RolePermissions:
    can_browse: bool                  # 浏览目录/详情/相册
    can_intake: bool                  # 一键入库
    can_manage_album: bool            # 相册管理（上传/AI 找图/提交）
    can_configure_keys: bool          # 个人密钥管理
    can_generate_itinerary: bool      # 生成个性化行程
    can_review: bool                  # 审核地标（review/publish）
    can_manage_landmarks: bool        # 条目管理（修改/下架/删除）
    can_manage_users: bool            # 用户管理（角色/封禁/删除）
    can_manage_system_keys: bool      # 系统级密钥


_LEVEL2 = RolePermissions(
    can_browse=True, can_intake=True, can_manage_album=True, can_configure_keys=True,
    can_generate_itinerary=False, can_review=False, can_manage_landmarks=False,
    can_manage_users=False, can_manage_system_keys=False,
)

_ROLE_MATRIX: dict[UserRole, RolePermissions] = {
    UserRole.LEVEL2: _LEVEL2,
    UserRole.LEVEL1: replace(_LEVEL2, can_generate_itinerary=True),
    UserRole.ADMIN: RolePermissions(
        can_browse=True, can_intake=True, can_manage_album=True, can_configure_keys=True,
        can_generate_itinerary=True, can_review=True, can_manage_landmarks=True,
        can_manage_users=True, can_manage_system_keys=True,
    ),
}


def normalize_role(value: str | UserRole | None) -> UserRole:
    if isinstance(value, UserRole):
        return value
    try:
        return UserRole(str(value or ""))
    except ValueError:
        return UserRole.LEVEL2


def role_at_least(role: str | UserRole | None, minimum: str | UserRole) -> bool:
    return _ROLE_ORDER[normalize_role(role)] >= _ROLE_ORDER[normalize_role(minimum)]


def permissions_for_role(role: str | UserRole | None) -> RolePermissions:
    return _ROLE_MATRIX[normalize_role(role)]
