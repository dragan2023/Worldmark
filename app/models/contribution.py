from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class LandmarkContribution(TimestampMixin, Base):
    """Attribution for one community-submitted candidate landmark."""

    __tablename__ = "landmark_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id", ondelete="RESTRICT"), index=True, nullable=False)
    contributor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contributor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    landmark: Mapped["Landmark"] = relationship(back_populates="contributions")
    contributor_user: Mapped["User | None"] = relationship(back_populates="landmark_contributions")
