"""Add search-result audit records and landmark review history.

Revision ID: 0002_content_review_audit
Revises: 0001_initial_schema
Create Date: 2026-08-10 00:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_content_review_audit"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    with op.batch_alter_table("search_runs") as batch_op:
        batch_op.add_column(sa.Column("quota_units", sa.Integer(), nullable=False, server_default="1"))

    verification = sa.Enum("candidate", "verified", "rejected", name="verificationstatus", native_enum=False, create_constraint=True)
    op.create_table(
        "search_reference_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("search_run_id", sa.Integer(), sa.ForeignKey("search_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("snippet", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_search_reference_records_search_run_id", "search_reference_records", ["search_run_id"])
    op.create_table(
        "landmark_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("landmark_id", sa.Integer(), sa.ForeignKey("landmarks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", verification, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewer_name", sa.String(255), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_landmark_reviews_landmark_id", "landmark_reviews", ["landmark_id"])


def downgrade() -> None:
    op.drop_index("ix_landmark_reviews_landmark_id", table_name="landmark_reviews")
    op.drop_table("landmark_reviews")
    op.drop_index("ix_search_reference_records_search_run_id", table_name="search_reference_records")
    op.drop_table("search_reference_records")
    with op.batch_alter_table("search_runs") as batch_op:
        batch_op.drop_column("quota_units")
