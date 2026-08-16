"""Add travel-planning inputs and generated references to itineraries.

Revision ID: 0006_itinerary_travel_planning
Revises: 0005_community_contributions
Create Date: 2026-08-13 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_itinerary_travel_planning"
down_revision: str | None = "0005_community_contributions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("origin_city", sa.String(100)))
    op.add_column("itineraries", sa.Column("return_city", sa.String(100)))
    op.add_column("itineraries", sa.Column("traveler_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("itineraries", sa.Column("budget_amount", sa.Integer()))
    op.add_column("itineraries", sa.Column("transport_preference", sa.String(50)))
    op.add_column("itineraries", sa.Column("auto_fill_nearby", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("itineraries", sa.Column("interests", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("itineraries", sa.Column("lodging_mode", sa.String(50), nullable=False, server_default="recommend"))
    op.add_column("itineraries", sa.Column("lodging_name", sa.String(255)))
    op.add_column("itineraries", sa.Column("lodging_address", sa.String(500)))
    op.add_column("itineraries", sa.Column("lodging_city", sa.String(100)))
    op.add_column("itineraries", sa.Column("lodging_reference", sa.JSON()))
    op.add_column("itineraries", sa.Column("transport_reference", sa.JSON()))
    op.add_column("itineraries", sa.Column("budget_summary", sa.JSON()))
    op.add_column("itinerary_days", sa.Column("supplemental_items", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("itinerary_days", "supplemental_items")
    for column in (
        "budget_summary", "transport_reference", "lodging_reference", "lodging_city", "lodging_address", "lodging_name",
        "lodging_mode", "interests", "auto_fill_nearby", "transport_preference", "budget_amount", "traveler_count",
        "return_city", "origin_city",
    ):
        op.drop_column("itineraries", column)
