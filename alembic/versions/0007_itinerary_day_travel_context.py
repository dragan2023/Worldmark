"""Store per-day lodging, city, and transport context.

Revision ID: 0007_itinerary_day_travel_context
Revises: 0006_itinerary_travel_planning
Create Date: 2026-08-13 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_itinerary_day_travel_context"
down_revision: str | None = "0006_itinerary_travel_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("itinerary_days", sa.Column("travel_context", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("itinerary_days", "travel_context")
