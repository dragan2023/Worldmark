from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.album import get_album_editor
from app.core.auth import require_admin
from app.db.session import get_db
from app.models.enums import VerificationStatus
from app.models.landmark import Landmark
from app.services.data_quality import LandmarkDataQualityService
from app.services.import_landmarks import LandmarkImportService
from app.services.landmark_album_editor import LandmarkAlbumEditorService, LandmarkAlbumNotFound
from app.services.review import LandmarkReviewService, ReviewValidationError
from app.services.search_discovery import SearchDiscoveryService
from app.integrations.search.bocha_web_search import SearchConfigurationError, SearchProviderError

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

class ReviewRequest(BaseModel):
    decision: VerificationStatus
    reason: str = Field(min_length=1, max_length=4000)
    reviewer_name: str = Field(min_length=1, max_length=255)

class SearchDiscoveryRequest(BaseModel):
    query_template: str = Field(min_length=1, max_length=500)
    query: str = Field(min_length=1, max_length=1000)

@router.post("/imports/landmarks", dependencies=[Depends(require_admin)])
async def import_landmarks(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, object]:
    if file.content_type not in {"text/csv", "application/vnd.ms-excel", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Only CSV uploads are supported.")
    result = LandmarkImportService(db).import_csv(await file.read())
    return {
        "imported_landmark_ids": result.imported_landmark_ids,
        "failures": [{"row_number": failure.row_number, "message": failure.message} for failure in result.failures],
    }

@router.post("/landmarks/{landmark_id}/review", dependencies=[Depends(require_admin)])
def review_landmark(landmark_id: int, payload: ReviewRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        landmark = LandmarkReviewService(db).review(landmark_id, payload.decision, payload.reason, payload.reviewer_name)
    except ReviewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": landmark.id, "verification_status": landmark.verification_status}

@router.post("/landmarks/{landmark_id}/publish", dependencies=[Depends(require_admin)])
def publish_landmark(landmark_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        landmark = LandmarkReviewService(db).publish(landmark_id)
    except ReviewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": landmark.id, "published_at": landmark.published_at}

@router.get("/data-quality", dependencies=[Depends(require_admin)])
def published_data_quality(db: Session = Depends(get_db)) -> dict[str, object]:
    issues = LandmarkDataQualityService(db).scan_published()
    return {"issues": [issue.__dict__ for issue in issues]}

@router.post("/search/discover", dependencies=[Depends(require_admin)])
def discover_candidates(payload: SearchDiscoveryRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        search_run = SearchDiscoveryService(db).discover(payload.query_template, payload.query)
    except SearchConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SearchProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "search_run_id": search_run.id,
        "request_id": search_run.provider_request_id,
        "reference_count": search_run.result_count,
    }


# ---------------------------------------------------------------- 条目管理（M5）


class LandmarkUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    transit_text: str | None = Field(default=None, max_length=4000)
    landmark_kind: str | None = Field(default=None, max_length=100)


def _admin_get_landmark(db: Session, landmark_id: int, include_deleted: bool = False):
    stmt = select(Landmark).where(Landmark.id == landmark_id)
    if include_deleted:
        stmt = stmt.execution_options(include_deleted=True)
    landmark = db.scalar(stmt)
    if landmark is None:
        raise HTTPException(status_code=404, detail="地标不存在。")
    return landmark


@router.get("/landmarks/{landmark_id}", dependencies=[Depends(require_admin)])
def admin_get_landmark(
    landmark_id: int,
    db: Session = Depends(get_db),
    editor: "LandmarkAlbumEditorService" = Depends(get_album_editor),
) -> dict[str, object]:
    """管理员查看条目完整内容（文字、来源、图片），供审核判定违规。"""
    landmark = _admin_get_landmark(db, landmark_id, include_deleted=True)

    try:
        album = editor.editor_snapshot(landmark.id)
    except LandmarkAlbumNotFound:
        album = {"published": [], "staged": []}
    photos = []
    for entry in album.get("published", []):
        photos.append({
            "kind": "published",
            "kind_label": "正式图",
            "url": entry.get("url"),
            "alt": entry.get("alt"),
            "caption": entry.get("caption"),
            "credit": entry.get("credit"),
            "license": entry.get("license"),
            "source_url": entry.get("source_url"),
        })
    for entry in album.get("staged", []):
        data = dict(entry)
        photos.append({
            "kind": data.get("kind"),
            "kind_label": "用户上传" if data.get("kind") == "upload" else "AI 找图",
            "url": data.get("url"),
            "alt": data.get("alt"),
            "caption": data.get("caption"),
            "credit": data.get("credit"),
            "license": data.get("license"),
            "source_url": data.get("source_url"),
        })

    sources = [
        {
            "url": link.source.url,
            "title": link.source.title,
            "publisher": link.source.publisher,
            "source_type": link.source.source_type,
            "accessed_at": link.source.accessed_at.isoformat() if link.source.accessed_at else None,
        }
        for link in landmark.sources
    ]
    contribution = min(landmark.contributions, key=lambda c: c.id, default=None)

    return {
        "id": landmark.id,
        "name": landmark.name,
        "description": landmark.description,
        "transit_text": landmark.transit_text,
        "landmark_kind": landmark.landmark_kind,
        "verification_status": landmark.verification_status.value if hasattr(landmark.verification_status, "value") else landmark.verification_status,
        "published_at": landmark.published_at.isoformat() if landmark.published_at else None,
        "deleted_at": landmark.deleted_at.isoformat() if landmark.deleted_at else None,
        "work_title": landmark.ip_work.title if landmark.ip_work else None,
        "work_aliases": landmark.ip_work.aliases if landmark.ip_work else None,
        "ip_type": landmark.ip_work.ip_type.value if landmark.ip_work and hasattr(landmark.ip_work.ip_type, "value") else None,
        "region": " / ".join(
            part
            for part in (landmark.location.province_name, landmark.location.city_name, landmark.location.district_name)
            if part
        ) if landmark.location else None,
        "address": landmark.location.normalized_address if landmark.location else None,
        "sources": sources,
        "contributor": contribution.contributor_name if contribution else None,
        "contributor_user_id": contribution.contributor_user_id if contribution else None,
        "photos": photos,
    }


@router.get("/landmarks", dependencies=[Depends(require_admin)])
def admin_list_landmarks(
    status_filter: str = Query(default="pending", alias="status", max_length=20),
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """地标管理列表：pending / verified / rejected / published / deleted / all。"""
    include_deleted = status_filter in ("deleted", "all")
    stmt = (
        select(Landmark)
        .options(selectinload(Landmark.ip_work), selectinload(Landmark.location))
        .order_by(Landmark.id.desc())
    )
    if include_deleted:
        stmt = stmt.execution_options(include_deleted=True)

    if status_filter == "pending":
        stmt = stmt.where(Landmark.verification_status == VerificationStatus.CANDIDATE, Landmark.deleted_at.is_(None))
    elif status_filter == "verified":
        stmt = stmt.where(Landmark.verification_status == VerificationStatus.VERIFIED, Landmark.deleted_at.is_(None))
    elif status_filter == "rejected":
        stmt = stmt.where(Landmark.verification_status == VerificationStatus.REJECTED, Landmark.deleted_at.is_(None))
    elif status_filter == "published":
        stmt = stmt.where(Landmark.published_at.is_not(None), Landmark.deleted_at.is_(None))
    elif status_filter == "deleted":
        stmt = stmt.where(Landmark.deleted_at.is_not(None))
    if q:
        stmt = stmt.where(Landmark.name.contains(q.strip()))

    total = len(db.scalars(stmt).all())
    landmarks = db.scalars(stmt.limit(limit).offset(offset)).all()
    ids = [item.id for item in landmarks]

    source_counts: dict[int, int] = {}
    contributors: dict[int, str] = {}
    if ids:
        from app.models.contribution import LandmarkContribution
        from app.models.source import LandmarkSource

        for lid, count in db.execute(
            select(LandmarkSource.landmark_id, func.count()).where(LandmarkSource.landmark_id.in_(ids)).group_by(LandmarkSource.landmark_id)
        ).all():
            source_counts[lid] = count
        for contribution in db.scalars(
            select(LandmarkContribution).where(LandmarkContribution.landmark_id.in_(ids)).order_by(LandmarkContribution.id.asc())
        ).all():
            contributors.setdefault(contribution.landmark_id, contribution.contributor_name)

    items = []
    for item in landmarks:
        region_parts = [
            item.location.province_name,
            item.location.city_name,
            item.location.district_name,
        ]
        items.append({
            "id": item.id,
            "name": item.name,
            "work_title": item.ip_work.title,
            "ip_type": item.ip_work.ip_type.value if hasattr(item.ip_work.ip_type, "value") else str(item.ip_work.ip_type),
            "region": " / ".join(part for part in region_parts if part),
            "verification_status": item.verification_status.value if hasattr(item.verification_status, "value") else str(item.verification_status),
            "published": item.published_at is not None,
            "deleted": item.deleted_at is not None,
            "source_count": source_counts.get(item.id, 0),
            "contributor": contributors.get(item.id),
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })
    return {"total": total, "items": items}


@router.patch("/landmarks/{landmark_id}", dependencies=[Depends(require_admin)])
def admin_update_landmark(
    landmark_id: int, payload: LandmarkUpdateRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    landmark = _admin_get_landmark(db, landmark_id)
    changed: list[str] = []
    for field in ("name", "description", "transit_text", "landmark_kind"):
        value = getattr(payload, field)
        if value is not None:
            setattr(landmark, field, value.strip())
            changed.append(field)
    db.commit()
    return {"id": landmark.id, "changed": changed}


@router.post("/landmarks/{landmark_id}/unpublish", dependencies=[Depends(require_admin)])
def admin_unpublish_landmark(landmark_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    from app.models.enums import PublicationStatus

    landmark = _admin_get_landmark(db, landmark_id)
    landmark.published_at = None
    landmark.ip_work.status = PublicationStatus.DRAFT
    db.commit()
    return {"id": landmark.id, "published": False}


@router.post("/landmarks/{landmark_id}/restore", dependencies=[Depends(require_admin)])
def admin_restore_landmark(landmark_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    from app.models.enums import PublicationStatus

    landmark = _admin_get_landmark(db, landmark_id, include_deleted=True)
    if landmark.deleted_at is not None:
        landmark.deleted_at = None
    landmark.ip_work.status = PublicationStatus.PUBLISHED if landmark.published_at else PublicationStatus.DRAFT
    db.commit()
    return {"id": landmark.id, "deleted": False}


@router.delete("/landmarks/{landmark_id}", dependencies=[Depends(require_admin)])
def admin_delete_landmark(landmark_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """软删：置 deleted_at，全局查询自动隐藏；可用 restore 恢复。"""
    from datetime import UTC, datetime

    landmark = _admin_get_landmark(db, landmark_id)
    landmark.deleted_at = datetime.now(UTC)
    db.commit()
    return {"id": landmark.id, "deleted": True}
