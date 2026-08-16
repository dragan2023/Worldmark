from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import PublicationStatus


class Route(TimestampMixin, Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip_work_id: Mapped[int | None] = mapped_column(ForeignKey("ip_works.id", ondelete="SET NULL"), index=True)
    city_name: Mapped[str | None] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    duration_text: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(
            PublicationStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=PublicationStatus.DRAFT,
        nullable=False,
    )

    ip_work: Mapped["IPWork | None"] = relationship(back_populates="routes")
    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete-orphan")


class RouteStop(TimestampMixin, Base):
    __tablename__ = "route_stops"
    __table_args__ = (UniqueConstraint("route_id", "stop_order", name="route_stop_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    landmark_id: Mapped[int] = mapped_column(ForeignKey("landmarks.id", ondelete="RESTRICT"), nullable=False)
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stay_minutes: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)

    route: Mapped["Route"] = relationship(back_populates="stops")
    landmark: Mapped["Landmark"] = relationship()
