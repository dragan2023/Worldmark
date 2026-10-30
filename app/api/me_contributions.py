"""当前用户自己的共创记录 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_member
from app.db.session import get_db
from app.services.contribution_records import list_user_contributions

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("/contributions")
def my_contributions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """只按贡献者本人过滤；被软删条目仅回传状态，不暴露已移除内容。"""
    return list_user_contributions(db, member.user_id, page=page, page_size=page_size)
