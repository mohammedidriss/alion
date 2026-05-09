"""consensus_event table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-09 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "consensus_event" not in insp.get_table_names():
        op.create_table(
            "consensus_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("t_ms", sa.Float(), nullable=False),
            sa.Column("hand", sa.String(length=10), nullable=False),
            sa.Column("velocity_ms", sa.Float(), nullable=False),
            sa.Column("punch_type", sa.String(length=20), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("sources", sa.String(length=80), nullable=False),
            sa.Column("second_pass_name", sa.String(length=40), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        )

    insp = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in insp.get_indexes("consensus_event")}
    if "ix_consensus_event_session_id" not in existing_indexes:
        op.create_index(
            "ix_consensus_event_session_id",
            "consensus_event",
            ["session_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_consensus_event_session_id", table_name="consensus_event")
    op.drop_table("consensus_event")
