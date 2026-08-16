from datetime import date
from typing import Any

from sqlalchemy import Date, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import IPType, ItineraryStatus


class Itinerary(TimestampMixin, Base):
    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    ip_work_id: Mapped[int | None] = mapped_column(ForeignKey("ip_works.id", ondelete="SET NULL"), index=True)
    ip_type: Mapped[IPType | None] = mapped_column(
        Enum(IPType, native_enum=False, create_constraint=True, values_callable=lambda enum: [item.value for item in enum])
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_country: Mapped[str | None] = mapped_column(String(2))
    destination_province: Mapped[str | None] = mapped_column(String(100))
    destination_city: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    companions: Mapped[str | None] = mapped_column(String(100))
    walking_preference: Mapped[str | None] = mapped_column(String(50))
    budget_tier: Mapped[str | None] = mapped_column(String(50))
    origin_city: Mapped[str | None] = mapped_column(String(100))
    return_city: Mapped[str | None] = mapped_column(String(100))
    traveler_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    budget_amount: Mapped[int | None] = mapped_column(Integer)
    transport_preference: Mapped[str | None] = mapped_column(String(50))
    auto_fill_nearby: Mapped[bool] = mapped_column(default=True, nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    lodging_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="recommend")
    lodging_name: Mapped[str | None] = mapped_column(String(255))
    lodging_address: Mapped[str | None] = mapped_column(String(500))
    lodging_city: Mapped[str | None] = mapped_column(String(100))
    lodging_reference: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    transport_reference: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    budget_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    free_text: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_landmark_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    used_landmark_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[ItineraryStatus] = mapped_column(
        Enum(
            ItineraryStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ItineraryStatus.QUEUED,
        nullable=False,
    )
    generation_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_duration_ms: Mapped[int | None] = mapped_column(Integer)
    validation_error_summary: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped["User"] = relationship(back_populates="itineraries")
    days: Mapped[list["ItineraryDay"]] = relationship(back_populates="itinerary", cascade="all, delete-orphan")


class ItineraryDay(TimestampMixin, Base):
    __tablename__ = "itinerary_days"
    __table_args__ = (UniqueConstraint("itinerary_id", "day_number", name="itinerary_day_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id", ondelete="CASCADE"), index=True, nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    itinerary_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    supplemental_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    travel_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    itinerary: Mapped["Itinerary"] = relationship(back_populates="days")
    stops: Mapped[list["ItineraryStop"]] = relationship(back_populates="day", cascade="all, delete-orphan")


class ItineraryStop(TimestampMixin, Base):
    __tablename__ = "itinerary_stops"
    __table_args__ = (UniqueConstraint("itinerary_day_id", "stop_order", name="itinerary_stop_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_day_id: Mapped[int] = mapped_column(ForeignKey("itinerary_days.id", ondelete="CASCADE"), index=True, nullable=False)
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id", ondelete="RESTRICT"), index=True, nullable=False)
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    time_slot: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text)

    day: Mapped["ItineraryDay"] = relationship(back_populates="stops")
    landmark: Mapped["Landmark"] = relationship()
