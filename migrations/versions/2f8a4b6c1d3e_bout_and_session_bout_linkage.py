"""bout, bell_event, and session bout linkage (ADR-011)

Revision ID: 2f8a4b6c1d3e
Revises: 1ca85f671aa5
Create Date: 2026-09-20

Two-fighter bouts (ADR-011). Adds:
- ``bout`` — a fight; owns the shared round config + result.
- ``bellevent`` — markers on the bout's shared round timeline (offsets from T_0).
- ``session.bout_id`` + ``session.corner`` — additive, nullable. NULL ``bout_id``
  means an ordinary single-fighter training session (today's path, unchanged).

Idempotent guards + SQLite batch mode, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f8a4b6c1d3e"
down_revision: str | Sequence[str] | None = "1ca85f671aa5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "bout" not in tables:
        op.create_table(
            "bout",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(), nullable=False),
            sa.Column("venue", sa.String(), nullable=True),
            sa.Column("round_count", sa.Integer(), nullable=False),
            sa.Column("round_duration_s", sa.Integer(), nullable=False),
            sa.Column("rest_duration_s", sa.Integer(), nullable=False),
            sa.Column("winner_corner", sa.String(), nullable=True),
            sa.Column("result_method", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "bellevent" not in tables:
        op.create_table(
            "bellevent",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("bout_id", sa.Uuid(), nullable=False),
            sa.Column("round_index", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("t_ms", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["bout_id"], ["bout.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_bellevent_bout_id", "bellevent", ["bout_id"], unique=False)

    session_cols = {c["name"] for c in insp.get_columns("session")}
    if "bout_id" not in session_cols and "corner" not in session_cols:
        with op.batch_alter_table("session") as batch:
            batch.add_column(sa.Column("bout_id", sa.Uuid(), nullable=True))
            batch.add_column(sa.Column("corner", sa.String(), nullable=True))
            batch.create_index("ix_session_bout_id", ["bout_id"], unique=False)
            batch.create_foreign_key("fk_session_bout_id", "bout", ["bout_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    session_cols = {c["name"] for c in insp.get_columns("session")}
    if "bout_id" in session_cols or "corner" in session_cols:
        existing_idx = {ix["name"] for ix in insp.get_indexes("session")}
        with op.batch_alter_table("session") as batch:
            # Drop the index (and, by column removal, its FK) before the column, so
            # SQLite batch mode doesn't try to re-create them on the rebuilt table.
            if "ix_session_bout_id" in existing_idx:
                batch.drop_index("ix_session_bout_id")
            if "corner" in session_cols:
                batch.drop_column("corner")
            if "bout_id" in session_cols:
                batch.drop_column("bout_id")

    tables = set(insp.get_table_names())
    if "bellevent" in tables:
        op.drop_table("bellevent")
    if "bout" in tables:
        op.drop_table("bout")
