from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import IPType, PublicationStatus


class IPWork(TimestampMixin, Base):
    __tablename__ = "ip_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    aliases: Mapped[str | None] = mapped_column(Text)
    ip_type: Mapped[IPType] = mapped_column(
        Enum(IPType, native_enum=False, create_constraint=True, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    creator: Mapped[str | None] = mapped_column(String(255))
    release_year: Mapped[int | None] = mapped_column(Integer)
    synopsis: Mapped[str | None] = mapped_column(Text)
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

    landmarks: Mapped[list["Landmark"]] = relationship(back_populates="ip_work")
    routes: Mapped[list["Route"]] = relationship(back_populates="ip_work")
