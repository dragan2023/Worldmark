"""Align users, landmarks and user_api_keys with the ORM models.

The first seven revisions predate the account system: ``users`` had no
``username`` / ``role`` / ``status`` / ``last_login_at``, ``landmarks`` had no
soft-delete column and ``user_api_keys`` did not exist.  A database created by
running ``alembic upgrade head`` therefore failed on login, soft delete and
personal API keys.

This revision is additive and idempotent per object: every column/table/index is
inspected before it is created so databases that were already patched by the
legacy ``scripts/migrate_user_roles.py`` script upgrade cleanly too.

Revision ID: 0008_user_schema_alignment
Revises: 0007_itinerary_day_travel_context
Create Date: 2026-10-22 00:00:00
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_user_schema_alignment"
down_revision: str | None = "0007_itinerary_day_travel_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_COLUMNS: dict[str, object] = {
    "role": lambda: sa.Column("role", sa.String(16), nullable=False, server_default="level2"),
    "status": lambda: sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    "last_login_at": lambda: sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
}

MAX_USERNAME_LENGTH = 32
_USERNAME_SAFE = re.compile(r"[^a-z0-9_]+")
USERNAME_SHAPE = re.compile(r"^[a-z0-9_]{3,32}$")


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table) if index.get("name")}


def _unique_constraint_names(table: str) -> set[str]:
    return {constraint["name"] for constraint in _inspector().get_unique_constraints(table) if constraint.get("name")}


def _normalize_username(raw: str) -> str:
    """Turn any e-mail local part into a legal deterministic username stem."""
    candidate = _USERNAME_SAFE.sub("_", (raw or "").strip().lower()).strip("_")
    if not candidate:
        candidate = "user"
    if not candidate[0].isalpha() and not candidate[0].isdigit():
        candidate = f"user_{candidate}"
    candidate = candidate[: MAX_USERNAME_LENGTH - 4].strip("_") or "user"
    if len(candidate) < 3:
        candidate = f"{candidate}_user"
    return candidate


def _backfill_usernames(connection) -> int:
    """Assign, normalize and de-duplicate usernames.

    Deterministic and collision-free: the e-mail local part is sanitised, then
    ``_<id>`` is appended whenever the stem is already taken.  Using the row id
    keeps the result stable across repeated runs and avoids the old
    ``name-2`` / ``name-2-2`` chaining.  Rows that were already patched by the
    legacy script are normalised in place instead of being rewritten blindly.
    """
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("email", sa.String),
        sa.column("username", sa.String(MAX_USERNAME_LENGTH)),
    )
    rows = connection.execute(
        sa.select(users.c.id, users.c.email, users.c.username).order_by(users.c.id)
    ).all()

    used: set[str] = set()
    changed = 0
    for user_id, email, current in rows:
        existing = current.strip().lower() if isinstance(current, str) else ""
        candidate = existing or _normalize_username((email or "").split("@", 1)[0])
        if not USERNAME_SHAPE.match(candidate):
            candidate = _normalize_username(candidate)
        if candidate in used:
            stem = candidate[: MAX_USERNAME_LENGTH - len(str(user_id)) - 1]
            candidate = f"{stem}_{user_id}"
            suffix = 2
            while candidate in used:
                tail = f"_{user_id}_{suffix}"
                candidate = f"{stem[: MAX_USERNAME_LENGTH - len(tail)]}{tail}"
                suffix += 1
        used.add(candidate)
        if candidate != current:
            connection.execute(
                sa.update(users).where(users.c.id == user_id).values(username=candidate)
            )
            changed += 1
    return changed


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------- users
    existing = _columns("users")
    for name, factory in USER_COLUMNS.items():
        if name not in existing:
            op.add_column("users", factory())

    if "username" not in existing:
        op.add_column("users", sa.Column("username", sa.String(MAX_USERNAME_LENGTH), nullable=True))

    username_column = sa.column("username", sa.String(MAX_USERNAME_LENGTH))
    _backfill_usernames(bind)

    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("is_admin", sa.Boolean),
        sa.column("role", sa.String),
        sa.column("status", sa.String),
        username_column,
    )
    bind.execute(
        sa.update(users_table)
        .where(sa.or_(users_table.c.role.is_(None), users_table.c.role == ""))
        .values(role="level2")
    )
    bind.execute(
        sa.update(users_table)
        .where(sa.or_(users_table.c.status.is_(None), users_table.c.status == ""))
        .values(status="active")
    )
    # Existing administrator flags stay authoritative; no new admins are created.
    bind.execute(
        sa.update(users_table)
        .where(users_table.c.is_admin.is_(True))
        .values(role="admin")
    )
    # Unknown/legacy role strings must not linger as privileged values.
    bind.execute(
        sa.update(users_table)
        .where(~users_table.c.role.in_(["admin", "level1", "level2"]))
        .values(role="level2")
    )
    bind.execute(
        sa.update(users_table)
        .where(~users_table.c.status.in_(["active", "banned"]))
        .values(status="active")
    )
    bind.execute(
        sa.update(users_table)
        .where(sa.or_(username_column.is_(None), username_column == ""))
        .values(username=sa.func.concat("user_", sa.cast(users_table.c.id, sa.String)))
    )

    indexes = _index_names("users")
    uniques = _unique_constraint_names("users")
    has_username_unique = any("username" in name for name in indexes | uniques)
    if not has_username_unique:
        op.create_index("ix_users_username", "users", ["username"], unique=True)
    if "ix_users_role" not in indexes:
        op.create_index("ix_users_role", "users", ["role"])

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "username",
            existing_type=sa.String(MAX_USERNAME_LENGTH),
            nullable=False,
        )

    # ------------------------------------------------------------ landmarks
    if "deleted_at" not in _columns("landmarks"):
        op.add_column("landmarks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_landmarks_deleted_at" not in _index_names("landmarks"):
        op.create_index("ix_landmarks_deleted_at", "landmarks", ["deleted_at"])

    # ------------------------------------------------------- user_api_keys
    table_names = set(_inspector().get_table_names())
    if "user_api_keys" not in table_names:
        op.create_table(
            "user_api_keys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_api_keys_user_id_users"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("encrypted_value", sa.String(512), nullable=False),
            sa.Column("key_hint", sa.String(32), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "provider", name="uq_user_api_keys_user_provider"),
        )
    if "ix_user_api_keys_user_id" not in _index_names("user_api_keys"):
        op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])


def downgrade() -> None:
    inspector = _inspector()
    if "user_api_keys" in set(inspector.get_table_names()):
        op.drop_table("user_api_keys")

    if "ix_landmarks_deleted_at" in _index_names("landmarks"):
        op.drop_index("ix_landmarks_deleted_at", table_name="landmarks")
    if "deleted_at" in _columns("landmarks"):
        op.drop_column("landmarks", "deleted_at")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("username")
    if "ix_users_role" in _index_names("users"):
        op.drop_index("ix_users_role", table_name="users")
    for name in ("last_login_at", "status", "role"):
        if name in _columns("users"):
            op.drop_column("users", name)
