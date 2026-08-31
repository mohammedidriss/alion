"""pulse_sample table

Revision ID: 53729c1636a1
Revises: a75a4d8f82d7
Create Date: 2026-05-22 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "53729c1636a1"
down_revision: str | Sequence[str] | None = "a75a4d8f82d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLModel.create_all may have already created the table at app startup;
    # tolerate that so the migration becomes a no-op in dev DBs.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "pulse_sample" in insp.get_table_names():
        return
    op.create_table(
        "pulse_sample",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Index created explicitly below — do NOT also pass index=True here
        # (create_table would emit the index and create_index() would collide
        # on a fresh DB).
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("t_ms", sa.Float(), nullable=False),
        sa.Column("ibi_ms", sa.Float(), nullable=False),
        sa.Column("pulse_bpm", sa.Float(), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False, server_default="rppg"),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
    )
    op.create_index("ix_pulse_sample_session_id", "pulse_sample", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pulse_sample_session_id", table_name="pulse_sample")
    op.drop_table("pulse_sample")
