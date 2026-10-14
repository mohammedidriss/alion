"""rq1_rating: the rater's account, and earlier scores kept (ADR-036)

Revision ID: a1c3e5f7b9d2
Revises: f7b9d1e3a5c7
Create Date: 2026-10-14

A score is tied to the signed-in rater (user_id) instead of a typed rater id,
and changing it keeps the old row (superseded_at) instead of overwriting it.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c3e5f7b9d2"
down_revision: str | Sequence[str] | None = "f7b9d1e3a5c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("rq1_rating")}


def upgrade() -> None:
    have = _columns()
    with op.batch_alter_table("rq1_rating") as batch:
        if "user_id" not in have:
            batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        if "superseded_at" not in have:
            batch.add_column(sa.Column("superseded_at", sa.DateTime(), nullable=True))
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("rq1_rating")}
    if "ix_rq1_rating_user_id" not in indexes:
        op.create_index("ix_rq1_rating_user_id", "rq1_rating", ["user_id"])


def downgrade() -> None:
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("rq1_rating")}
    if "ix_rq1_rating_user_id" in indexes:
        op.drop_index("ix_rq1_rating_user_id", table_name="rq1_rating")
    have = _columns()
    with op.batch_alter_table("rq1_rating") as batch:
        if "superseded_at" in have:
            batch.drop_column("superseded_at")
        if "user_id" in have:
            batch.drop_column("user_id")
