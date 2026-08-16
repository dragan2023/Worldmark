from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(500))
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    license_note: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)

    landmarks: Mapped[list["LandmarkSource"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class LandmarkSource(TimestampMixin, Base):
    __tablename__ = "landmark_sources"

    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    claim_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    landmark: Mapped["Landmark"] = relationship(back_populates="sources")
    source: Mapped["Source"] = relationship(back_populates="landmarks")
