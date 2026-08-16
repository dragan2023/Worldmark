from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.contribution import LandmarkContribution
from app.services.import_landmarks import CandidateRow, LandmarkImportService


@dataclass(frozen=True)
class ContributionReceipt:
    contribution_id: int
    landmark_id: int
    contributor_name: str


class CommunityContributionService:
    """Adds attributable submissions while retaining the existing candidate review flow."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def submit(self, contributor_name: str, candidate: CandidateRow, contributor_user_id: int | None = None) -> ContributionReceipt:
        try:
            landmark = LandmarkImportService(self._db).create_candidate(candidate)
            contribution = LandmarkContribution(
                landmark_id=landmark.id,
                contributor_name=contributor_name.strip(),
                contributor_user_id=contributor_user_id,
            )
            self._db.add(contribution)
            self._db.commit()
            self._db.refresh(contribution)
        except Exception:
            self._db.rollback()
            raise
        return ContributionReceipt(contribution.id, landmark.id, contribution.contributor_name)
