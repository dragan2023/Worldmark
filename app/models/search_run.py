from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SearchRun(TimestampMixin, Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    query_template: Mapped[str] = mapped_column(String(500), nullable=False)
    query_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)

    references: Mapped[list["SearchReferenceRecord"]] = relationship(
        back_populates="search_run", cascade="all, delete-orphan"
    )


class SearchReferenceRecord(TimestampMixin, Base):
    __tablename__ = "search_reference_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)

    search_run: Mapped["SearchRun"] = relationship(back_populates="references")
