from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import PublicationStatus, VerificationStatus
from app.models.landmark import Landmark
from app.models.review import LandmarkReview


class ReviewValidationError(ValueError):
    """Raised when a content-review transition is invalid."""


class LandmarkReviewService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def review(self, landmark_id: int, decision: VerificationStatus, reason: str, reviewer_name: str) -> Landmark:
        if decision not in {VerificationStatus.VERIFIED, VerificationStatus.REJECTED}:
            raise ReviewValidationError("Review decision must be verified or rejected.")
        landmark = self._get_landmark(landmark_id)
        if not reason.strip() or not reviewer_name.strip():
            raise ReviewValidationError("A review reason and reviewer name are required.")

        landmark.verification_status = decision
        self._db.add(LandmarkReview(
            landmark_id=landmark.id, decision=decision, reason=reason.strip(), reviewer_name=reviewer_name.strip()
        ))
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def publish(self, landmark_id: int) -> Landmark:
        landmark = self._get_landmark(landmark_id)
        if landmark.verification_status != VerificationStatus.VERIFIED:
            raise ReviewValidationError("Only verified landmarks can be published.")
        if not landmark.sources:
            raise ReviewValidationError("A landmark needs at least one source before publication.")

        landmark.published_at = datetime.now(UTC)
        landmark.ip_work.status = PublicationStatus.PUBLISHED
        self._db.commit()
        self._db.refresh(landmark)
        return landmark

    def _get_landmark(self, landmark_id: int) -> Landmark:
        landmark = self._db.scalar(
            select(Landmark)
            .options(selectinload(Landmark.sources), selectinload(Landmark.ip_work))
            .where(Landmark.id == landmark_id)
        )
        if landmark is None:
            raise ReviewValidationError("Landmark not found.")
        return landmark
