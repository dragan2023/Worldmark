"""当前用户共创记录的查询逻辑（API 与页面共用，避免两套口径）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.contribution import LandmarkContribution
from app.models.enums import PublicationStatus, VerificationStatus
from app.models.landmark import Landmark
from app.models.review import LandmarkReview

REVIEW_DECISION_LABELS = {"candidate": "待审核", "verified": "已核验", "rejected": "已拒绝"}
STATUS_LABELS = {
    "candidate": "待审核",
    "verified_pending_publish": "已核验，待发布",
    "published": "已发布",
    "rejected": "已拒绝",
    "deleted": "已下架删除",
}


def contribution_status(landmark: Landmark) -> str:
    if landmark.deleted_at is not None:
        return "deleted"
    if landmark.verification_status == VerificationStatus.REJECTED:
        return "rejected"
    if (
        landmark.published_at is not None
        and landmark.ip_work is not None
        and landmark.ip_work.status == PublicationStatus.PUBLISHED
    ):
        return "published"
    if landmark.verification_status == VerificationStatus.VERIFIED:
        return "verified_pending_publish"
    return "candidate"


def _enum_value(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def list_user_contributions(db: Session, user_id: int, page: int = 1, page_size: int = 10) -> dict[str, object]:
    condition = LandmarkContribution.contributor_user_id == user_id
    total = int(
        db.scalar(select(func.count(func.distinct(LandmarkContribution.landmark_id))).where(condition)) or 0
    )
    rows = db.execute(
        select(LandmarkContribution.landmark_id)
        .where(condition)
        .group_by(LandmarkContribution.landmark_id)
        .order_by(func.max(LandmarkContribution.id).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    landmark_ids = [row[0] for row in rows]

    items: list[dict[str, object]] = []
    if landmark_ids:
        landmarks = db.scalars(
            select(Landmark)
            .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
            .where(Landmark.id.in_(landmark_ids))
            .execution_options(include_deleted=True)
        ).all()
        by_id = {landmark.id: landmark for landmark in landmarks}
        reviews: dict[int, LandmarkReview] = {}
        for review in db.scalars(
            select(LandmarkReview)
            .where(LandmarkReview.landmark_id.in_(landmark_ids))
            .order_by(LandmarkReview.id.desc())
        ).all():
            reviews.setdefault(review.landmark_id, review)

        for landmark_id in landmark_ids:
            landmark = by_id.get(landmark_id)
            if landmark is None:
                continue
            status = contribution_status(landmark)
            latest = reviews.get(landmark_id)
            decision = _enum_value(latest.decision) if latest else None
            items.append({
                "landmark_id": landmark.id,
                "name": landmark.name if status != "deleted" else None,
                "work_title": landmark.ip_work.title if landmark.ip_work and status != "deleted" else None,
                "region": " / ".join(
                    part for part in (
                        landmark.location.province_name if landmark.location else None,
                        landmark.location.city_name if landmark.location else None,
                    ) if part
                ) or None,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "updated_at": landmark.updated_at,
                "review_feedback": {
                    "decision": decision,
                    "decision_label": REVIEW_DECISION_LABELS.get(decision or ""),
                    "reason": latest.reason if latest else None,
                    "reviewed_at": latest.created_at if latest else None,
                } if latest else None,
                # 仅未删除的自家条目可继续编辑（保存后进入重新审核）
                "can_edit": status != "deleted",
            })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total else 1,
        "items": items,
    }
