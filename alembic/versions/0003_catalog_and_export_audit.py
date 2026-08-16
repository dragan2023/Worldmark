"""Add catalog query indexes and minimal export audit records.

Revision ID: 0003_catalog_and_export_audit
Revises: 0002_content_review_audit
Create Date: 2026-08-10 01:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_catalog_and_export_audit"
down_revision: str | None = "0002_content_review_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_index("ix_landmarks_catalog_published", "landmarks", ["published_at", "ip_work_id", "location_id"])
    op.create_index("ix_locations_catalog_region", "locations", ["country_code", "province_name", "city_name"])
    op.create_table(
        "export_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_kind", sa.String(20), nullable=False, server_default="anonymous"),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("ip_type", sa.String(20)),
        sa.Column("result_count", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_export_events_user_id", "export_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_export_events_user_id", table_name="export_events")
    op.drop_table("export_events")
    op.drop_index("ix_locations_catalog_region", table_name="locations")
    op.drop_index("ix_landmarks_catalog_published", table_name="landmarks")
