"""地标编辑权限：贡献者或管理员可修改；管理员即时生效，贡献者需重新审核。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contribution import LandmarkContribution
from app.models.enums import UserRole
from app.models.landmark import Landmark
from app.services.permissions import normalize_role


class LandmarkAccessError(Exception):
    """无权修改该地标（由 API 层映射为 403/404）。"""


def get_landmark_for_edit(db: Session, member, landmark_id: int) -> tuple[Landmark, bool]:
    """返回 (地标, 是否管理员)。

    - 地标不存在或已软删 → LandmarkAccessError("地标不存在。")
    - 管理员 → 放行（is_admin=True，修改即时生效）
    - 贡献者（contributions.contributor_user_id 匹配）→ 放行（is_admin=False，修改进入重新审核）
    - 其他登录用户 → LandmarkAccessError（无权修改）
    """
    landmark = db.get(Landmark, landmark_id)  # 软删全局过滤：已删地标取不到
    if landmark is None:
        raise LandmarkAccessError("地标不存在。")

    if member is None or member.user_id is None:
        raise LandmarkAccessError("请先登录。")

    role = normalize_role(member.role)
    if role == UserRole.ADMIN:
        return landmark, True

    contribution = db.scalar(
        select(LandmarkContribution).where(
            LandmarkContribution.landmark_id == landmark_id,
            LandmarkContribution.contributor_user_id == member.user_id,
        )
    )
    if contribution is None:
        raise LandmarkAccessError("只有该地标的贡献者或管理员可以修改。")
    return landmark, False
