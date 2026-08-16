from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Location(TimestampMixin, Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), index=True, nullable=False)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    province_name: Mapped[str | None] = mapped_column(String(100), index=True)
    city_name: Mapped[str | None] = mapped_column(String(100), index=True)
    district_name: Mapped[str | None] = mapped_column(String(100))
    normalized_address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    landmarks: Mapped[list["Landmark"]] = relationship(back_populates="location")
