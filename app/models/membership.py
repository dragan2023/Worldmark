from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import MembershipTier


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    tier: Mapped[MembershipTier] = mapped_column(
        Enum(
            MembershipTier,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MembershipTier.FREE,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="membership")
