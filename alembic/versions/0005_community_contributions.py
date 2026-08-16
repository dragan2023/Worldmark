"""Add attributable community landmark submissions.

Revision ID: 0005_community_contributions
Revises: 0004_itineraries
Create Date: 2026-08-11 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_community_contributions"
down_revision: str | None = "0004_itineraries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "landmark_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("landmark_id", sa.Integer(), sa.ForeignKey("landmarks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contributor_name", sa.String(100), nullable=False),
        sa.Column("contributor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_landmark_contributions_landmark_id", "landmark_contributions", ["landmark_id"])
    op.create_index("ix_landmark_contributions_contributor_user_id", "landmark_contributions", ["contributor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_landmark_contributions_contributor_user_id", table_name="landmark_contributions")
    op.drop_index("ix_landmark_contributions_landmark_id", table_name="landmark_contributions")
    op.drop_table("landmark_contributions")
