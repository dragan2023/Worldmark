from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import VerificationStatus
from app.models.landmark import Landmark


@dataclass(frozen=True)
class DataIssue:
    landmark_id: int
    code: str
    message: str


class LandmarkDataQualityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def check_landmark(self, landmark: Landmark) -> list[DataIssue]:
        issues: list[DataIssue] = []
        if not landmark.location.country_code or not landmark.location.country_name or not landmark.location.normalized_address:
            issues.append(DataIssue(landmark.id, "missing_geography", "Country and normalized address are required."))
        if not landmark.description.strip():
            issues.append(DataIssue(landmark.id, "missing_description", "A landmark description is required."))
        if not landmark.sources:
            issues.append(DataIssue(landmark.id, "missing_source", "At least one source is required."))
        if landmark.published_at and landmark.verification_status != VerificationStatus.VERIFIED:
            issues.append(DataIssue(landmark.id, "published_unverified", "Published landmarks must be verified."))
        return issues

    def scan_published(self) -> list[DataIssue]:
        landmarks = self._db.scalars(
            select(Landmark)
            .options(selectinload(Landmark.location), selectinload(Landmark.sources))
            .where(Landmark.published_at.is_not(None))
        ).all()
        return [issue for landmark in landmarks for issue in self.check_landmark(landmark)]
