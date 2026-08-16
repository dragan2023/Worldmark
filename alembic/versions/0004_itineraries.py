"""Add structured premium itineraries.

Revision ID: 0004_itineraries
Revises: 0003_catalog_and_export_audit
Create Date: 2026-08-10 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_itineraries"
down_revision: str | None = "0003_catalog_and_export_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    ip_type = sa.Enum("literature", "game", "screen", name="iptype", native_enum=False, create_constraint=True)
    itinerary_status = sa.Enum("queued", "running", "succeeded", "failed", name="itinerarystatus", native_enum=False, create_constraint=True)
    op.create_table(
        "itineraries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip_work_id", sa.Integer(), sa.ForeignKey("ip_works.id", ondelete="SET NULL")),
        sa.Column("ip_type", ip_type),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("destination_country", sa.String(2)), sa.Column("destination_province", sa.String(100)), sa.Column("destination_city", sa.String(100)),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date(), nullable=False), sa.Column("daily_hours", sa.Integer(), nullable=False),
        sa.Column("companions", sa.String(100)), sa.Column("walking_preference", sa.String(50)), sa.Column("budget_tier", sa.String(50)), sa.Column("free_text", sa.Text()),
        sa.Column("input_snapshot", sa.JSON(), nullable=False), sa.Column("candidate_landmark_ids", sa.JSON(), nullable=False), sa.Column("used_landmark_ids", sa.JSON(), nullable=False),
        sa.Column("generator_version", sa.String(100), nullable=False), sa.Column("prompt_version", sa.String(100)),
        sa.Column("status", itinerary_status, nullable=False, server_default="queued"), sa.Column("generation_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_duration_ms", sa.Integer()), sa.Column("validation_error_summary", sa.String(1000)), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
    )
    op.create_index("ix_itineraries_user_id", "itineraries", ["user_id"])
    op.create_index("ix_itineraries_ip_work_id", "itineraries", ["ip_work_id"])
    op.create_table(
        "itinerary_days", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("itinerary_id", sa.Integer(), sa.ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False), sa.Column("itinerary_date", sa.Date(), nullable=False), sa.Column("summary", sa.Text()),
        *_timestamps(), sa.UniqueConstraint("itinerary_id", "day_number", name="itinerary_day_number"),
    )
    op.create_index("ix_itinerary_days_itinerary_id", "itinerary_days", ["itinerary_id"])
    op.create_table(
        "itinerary_stops", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("itinerary_day_id", sa.Integer(), sa.ForeignKey("itinerary_days.id", ondelete="CASCADE"), nullable=False),
        sa.Column("landmark_id", sa.Integer(), sa.ForeignKey("landmarks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("stop_order", sa.Integer(), nullable=False), sa.Column("time_slot", sa.String(20), nullable=False), sa.Column("planned_minutes", sa.Integer(), nullable=False), sa.Column("selection_reason", sa.Text(), nullable=False), sa.Column("user_note", sa.Text()),
        *_timestamps(), sa.UniqueConstraint("itinerary_day_id", "stop_order", name="itinerary_stop_order"),
    )
    op.create_index("ix_itinerary_stops_itinerary_day_id", "itinerary_stops", ["itinerary_day_id"])
    op.create_index("ix_itinerary_stops_landmark_id", "itinerary_stops", ["landmark_id"])


def downgrade() -> None:
    op.drop_index("ix_itinerary_stops_landmark_id", table_name="itinerary_stops")
    op.drop_index("ix_itinerary_stops_itinerary_day_id", table_name="itinerary_stops")
    op.drop_table("itinerary_stops")
    op.drop_index("ix_itinerary_days_itinerary_id", table_name="itinerary_days")
    op.drop_table("itinerary_days")
    op.drop_index("ix_itineraries_ip_work_id", table_name="itineraries")
    op.drop_index("ix_itineraries_user_id", table_name="itineraries")
    op.drop_table("itineraries")
