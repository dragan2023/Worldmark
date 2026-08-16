from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
class ExportEvent(TimestampMixin, Base):
    """Minimal export audit record without retaining selected regional filters."""

    __tablename__ = "export_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="anonymous")
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    ip_type: Mapped[str | None] = mapped_column(String(20))
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
