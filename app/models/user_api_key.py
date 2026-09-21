from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserApiKey(TimestampMixin, Base):
    """用户自配的第三方服务密钥（静态加密存储，接口永不回传明文）。"""

    __tablename__ = "user_api_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # deepseek / amap / bocha / meituan
    encrypted_value: Mapped[str] = mapped_column(String(512), nullable=False)
    key_hint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
