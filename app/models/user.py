from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    membership: Mapped["Membership | None"] = relationship(back_populates="user", uselist=False)
    itineraries: Mapped[list["Itinerary"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    landmark_contributions: Mapped[list["LandmarkContribution"]] = relationship(back_populates="contributor_user")
