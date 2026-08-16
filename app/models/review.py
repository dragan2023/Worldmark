from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import VerificationStatus


class LandmarkReview(TimestampMixin, Base):
    __tablename__ = "landmark_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id", ondelete="CASCADE"), index=True)
    decision: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    landmark: Mapped["Landmark"] = relationship(back_populates="reviews")
