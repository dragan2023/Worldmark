"""贡献者修改自己提交的地标内容。

- 管理员：修改即时生效，不进入审核流程。
- 贡献者：修改后地标回到「待审核」并暂时下架，重新通过审核后才再次上架。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, require_member
from app.db.session import get_db
from app.models.enums import PublicationStatus, VerificationStatus
from app.services.landmark_access import LandmarkAccessError, get_landmark_for_edit

router = APIRouter(prefix="/api/v1/landmarks", tags=["contributor"])


class LandmarkContentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    transit_text: str | None = Field(default=None, max_length=4000)
    landmark_kind: str | None = Field(default=None, max_length=100)


@router.get("/{landmark_id}/content")
def get_landmark_content(
    landmark_id: int,
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """贡献者/管理员读取可编辑的地标内容（不受上架状态限制）。"""
    try:
        landmark, is_admin = get_landmark_for_edit(db, member, landmark_id)
    except LandmarkAccessError as exc:
        status_code = 404 if "不存在" in str(exc) else 403
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return {
        "id": landmark.id,
        "name": landmark.name,
        "description": landmark.description,
        "transit_text": landmark.transit_text,
        "landmark_kind": landmark.landmark_kind,
        "verification_status": landmark.verification_status.value
        if hasattr(landmark.verification_status, "value")
        else str(landmark.verification_status),
        "published": landmark.published_at is not None,
        "is_admin": is_admin,
    }


@router.patch("/{landmark_id}/content")
def update_landmark_content(
    landmark_id: int,
    payload: LandmarkContentUpdate,
    member: CurrentMember = Depends(require_member),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        landmark, is_admin = get_landmark_for_edit(db, member, landmark_id)
    except LandmarkAccessError as exc:
        status_code = 404 if "不存在" in str(exc) else 403
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    changed: list[str] = []
    for field in ("name", "description", "transit_text", "landmark_kind"):
        value = getattr(payload, field)
        if value is not None:
            setattr(landmark, field, value.strip())
            changed.append(field)
    if not changed:
        raise HTTPException(status_code=422, detail="没有需要修改的内容。")

    review_required = not is_admin
    if review_required:
        landmark.verification_status = VerificationStatus.CANDIDATE
        landmark.published_at = None
        landmark.ip_work.status = PublicationStatus.DRAFT

    db.commit()
    return {
        "id": landmark.id,
        "changed": changed,
        "review_required": review_required,
        "verification_status": landmark.verification_status.value
        if hasattr(landmark.verification_status, "value")
        else str(landmark.verification_status),
        "note": "修改已提交，进入重新审核；重新审核通过前将暂时下架。" if review_required else "修改已即时生效。",
    }
