from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import CurrentMember, get_current_member
from app.db.session import get_db
from app.services.community_contributions import CommunityContributionService
from app.services.import_landmarks import CandidateRow


router = APIRouter(prefix="/api/v1/contributions", tags=["contributions"])


class CommunityLandmarkRequest(CandidateRow):
    contributor_name: str = Field(min_length=1, max_length=100)
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: str = Field(default="community", min_length=1, max_length=100)
    claim_scope: str = "work_association"

    @field_validator("description")
    @classmethod
    def require_three_part_description(cls, value: str) -> str:
        required = ("在作品中的重要地位：", "主要出现的情节：", "现实地标介绍：")
        if not all(part in value for part in required):
            raise ValueError("description must include the three required landmark-introduction sections")
        return value


@router.post("/landmarks", status_code=status.HTTP_201_CREATED)
def submit_landmark_contribution(
    payload: CommunityLandmarkRequest,
    member: CurrentMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        receipt = CommunityContributionService(db).submit(
            payload.contributor_name,
            CandidateRow.model_validate(payload.model_dump(exclude={"contributor_name"})),
            member.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "contribution_id": receipt.contribution_id,
        "landmark_id": receipt.landmark_id,
        "contributor_name": receipt.contributor_name,
        "verification_status": "candidate",
        "message": "Submission recorded and awaiting review.",
    }
