from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import VerificationStatus


class Landmark(TimestampMixin, Base):
    __tablename__ = "landmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip_work_id: Mapped[int] = mapped_column(ForeignKey("ip_works.id", ondelete="RESTRICT"), index=True, nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    transit_text: Mapped[str | None] = mapped_column(Text)
    landmark_kind: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=VerificationStatus.CANDIDATE,
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    ip_work: Mapped["IPWork"] = relationship(back_populates="landmarks")
    location: Mapped["Location"] = relationship(back_populates="landmarks")
    sources: Mapped[list["LandmarkSource"]] = relationship(back_populates="landmark", cascade="all, delete-orphan")
    reviews: Mapped[list["LandmarkReview"]] = relationship(back_populates="landmark", cascade="all, delete-orphan")
    contributions: Mapped[list["LandmarkContribution"]] = relationship(back_populates="landmark")
