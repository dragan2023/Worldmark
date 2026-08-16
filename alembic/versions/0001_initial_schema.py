"""Create the initial IP landmark tourism schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    tier = sa.Enum("free", "lite", "premium", name="membershiptier", native_enum=False, create_constraint=True)
    ip_type = sa.Enum("literature", "game", "screen", name="iptype", native_enum=False, create_constraint=True)
    publish = sa.Enum("draft", "published", "archived", name="publicationstatus", native_enum=False, create_constraint=True)
    verification = sa.Enum("candidate", "verified", "rejected", name="verificationstatus", native_enum=False, create_constraint=True)
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()), *_timestamps())
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table("ip_works", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(255), nullable=False), sa.Column("aliases", sa.Text()), sa.Column("ip_type", ip_type, nullable=False), sa.Column("creator", sa.String(255)), sa.Column("release_year", sa.Integer()), sa.Column("synopsis", sa.Text()), sa.Column("status", publish, nullable=False, server_default="draft"), *_timestamps())
    op.create_index("ix_ip_works_title", "ip_works", ["title"])
    op.create_table("locations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("country_code", sa.String(2), nullable=False), sa.Column("country_name", sa.String(100), nullable=False), sa.Column("province_name", sa.String(100)), sa.Column("city_name", sa.String(100)), sa.Column("district_name", sa.String(100)), sa.Column("normalized_address", sa.String(500), nullable=False), sa.Column("latitude", sa.Float()), sa.Column("longitude", sa.Float()), *_timestamps())
    op.create_index("ix_locations_country_code", "locations", ["country_code"])
    op.create_index("ix_locations_province_name", "locations", ["province_name"])
    op.create_index("ix_locations_city_name", "locations", ["city_name"])
    op.create_table("sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("url", sa.String(2048), nullable=False, unique=True), sa.Column("publisher", sa.String(255)), sa.Column("title", sa.String(500)), sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("license_note", sa.Text()), sa.Column("source_type", sa.String(100), nullable=False), *_timestamps())
    op.create_table("memberships", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("tier", tier, nullable=False, server_default="free"), sa.Column("expires_at", sa.DateTime(timezone=True)), *_timestamps())
    op.create_table("landmarks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("ip_work_id", sa.Integer(), sa.ForeignKey("ip_works.id", ondelete="RESTRICT"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("transit_text", sa.Text()), sa.Column("landmark_kind", sa.String(100)), sa.Column("verification_status", verification, nullable=False, server_default="candidate"), sa.Column("published_at", sa.DateTime(timezone=True)), *_timestamps())
    op.create_index("ix_landmarks_ip_work_id", "landmarks", ["ip_work_id"])
    op.create_index("ix_landmarks_location_id", "landmarks", ["location_id"])
    op.create_index("ix_landmarks_published_at", "landmarks", ["published_at"])
    op.create_table("routes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("ip_work_id", sa.Integer(), sa.ForeignKey("ip_works.id", ondelete="SET NULL")), sa.Column("city_name", sa.String(100)), sa.Column("title", sa.String(255), nullable=False), sa.Column("summary", sa.Text()), sa.Column("duration_text", sa.String(100)), sa.Column("status", publish, nullable=False, server_default="draft"), *_timestamps())
    op.create_index("ix_routes_ip_work_id", "routes", ["ip_work_id"])
    op.create_index("ix_routes_city_name", "routes", ["city_name"])
    op.create_table("route_stops", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False), sa.Column("landmark_id", sa.Integer(), sa.ForeignKey("landmarks.id", ondelete="RESTRICT"), nullable=False), sa.Column("stop_order", sa.Integer(), nullable=False), sa.Column("stay_minutes", sa.Integer()), sa.Column("note", sa.Text()), *_timestamps(), sa.UniqueConstraint("route_id", "stop_order", name="route_stop_order"))
    op.create_table("landmark_sources", sa.Column("landmark_id", sa.Integer(), sa.ForeignKey("landmarks.id", ondelete="CASCADE"), primary_key=True), sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True), sa.Column("claim_scope", sa.String(100), nullable=False), sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reviewed_at", sa.DateTime(timezone=True)), *_timestamps())
    op.create_table("search_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("provider", sa.String(100), nullable=False), sa.Column("query_template", sa.String(500), nullable=False), sa.Column("query_text", sa.String(1000), nullable=False), sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False), sa.Column("provider_request_id", sa.String(255), unique=True), sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("status", sa.String(50), nullable=False), sa.Column("error_summary", sa.Text()), *_timestamps())


def downgrade() -> None:
    op.drop_table("search_runs")
    op.drop_table("landmark_sources")
    op.drop_table("route_stops")
    op.drop_index("ix_routes_city_name", table_name="routes")
    op.drop_index("ix_routes_ip_work_id", table_name="routes")
    op.drop_table("routes")
    op.drop_index("ix_landmarks_published_at", table_name="landmarks")
    op.drop_index("ix_landmarks_location_id", table_name="landmarks")
    op.drop_index("ix_landmarks_ip_work_id", table_name="landmarks")
    op.drop_table("landmarks")
    op.drop_table("memberships")
    op.drop_table("sources")
    op.drop_index("ix_locations_city_name", table_name="locations")
    op.drop_index("ix_locations_province_name", table_name="locations")
    op.drop_index("ix_locations_country_code", table_name="locations")
    op.drop_table("locations")
    op.drop_index("ix_ip_works_title", table_name="ip_works")
    op.drop_table("ip_works")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
