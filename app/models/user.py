from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="level2", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    membership: Mapped["Membership | None"] = relationship(back_populates="user", uselist=False)
    itineraries: Mapped[list["Itinerary"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    landmark_contributions: Mapped[list["LandmarkContribution"]] = relationship(back_populates="contributor_user")
