"""head_impact_event table

Revision ID: a75a4d8f82d7
Revises: 1ca85f671aa5
Create Date: 2026-05-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a75a4d8f82d7"
down_revision: str | Sequence[str] | None = "1ca85f671aa5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLModel.create_all may have already created the table at app startup;
    # tolerate that so the migration becomes a no-op in dev DBs.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "head_impact_event" in insp.get_table_names():
        return
    op.create_table(
        "head_impact_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Index created explicitly below — do NOT also pass index=True here,
        # or create_table emits the index and the create_index() collides on
        # a fresh DB (only masked when the table pre-exists via create_all).
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("t_ms", sa.Float(), nullable=False),
        sa.Column("peak_linear_accel_g", sa.Float(), nullable=False),
        sa.Column("peak_rotational_vel_rad_s", sa.Float(), nullable=False),
        sa.Column("peak_rotational_accel_rad_s2", sa.Float(), nullable=True),
        sa.Column("location", sa.String(length=10), nullable=False),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
    )
    op.create_index(
        "ix_head_impact_event_session_id", "head_impact_event", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_head_impact_event_session_id", table_name="head_impact_event")
    op.drop_table("head_impact_event")
