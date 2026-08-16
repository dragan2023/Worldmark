import secrets

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.enums import VerificationStatus
from app.models.contribution import LandmarkContribution
from app.models.landmark import Landmark
from app.services.data_quality import LandmarkDataQualityService
from app.services.import_landmarks import LandmarkImportService
from app.services.review import LandmarkReviewService, ReviewValidationError
from app.services.search_discovery import SearchDiscoveryService
from app.integrations.search.bocha_web_search import SearchConfigurationError, SearchProviderError

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(
    x_admin_token: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    configured_token = settings.admin_api_token.get_secret_value() if settings.admin_api_token else None
    if not configured_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin API is not configured.")
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, configured_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


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


@router.get("/contributions", dependencies=[Depends(require_admin)])
def list_community_contributions(db: Session = Depends(get_db)) -> dict[str, object]:
    contributions = db.scalars(
        select(LandmarkContribution)
        .options(selectinload(LandmarkContribution.landmark).selectinload(Landmark.ip_work))
        .order_by(LandmarkContribution.created_at.desc(), LandmarkContribution.id.desc())
    ).all()
    return {
        "items": [
            {
                "id": contribution.id,
                "contributor_name": contribution.contributor_name,
                "contributor_user_id": contribution.contributor_user_id,
                "submitted_at": contribution.created_at,
                "landmark_id": contribution.landmark_id,
                "landmark_name": contribution.landmark.name,
                "work_title": contribution.landmark.ip_work.title,
                "verification_status": contribution.landmark.verification_status,
            }
            for contribution in contributions
        ]
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
