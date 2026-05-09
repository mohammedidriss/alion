"""imu_sample table

Revision ID: a1b2c3d4e5f6
Revises: c0dc926843da
Create Date: 2026-05-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c0dc926843da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLModel.create_all may have already created the table at app startup;
    # tolerate that so the migration becomes a no-op in dev DBs.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "imu_sample" in insp.get_table_names():
        return
    op.create_table(
        "imu_sample",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("t_ms", sa.Float(), nullable=False),
        sa.Column("ax_g", sa.Float(), nullable=False),
        sa.Column("ay_g", sa.Float(), nullable=False),
        sa.Column("az_g", sa.Float(), nullable=False),
        sa.Column("gx_dps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gy_dps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gz_dps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hand", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
    )
    op.create_index(
        "ix_imu_sample_session_id", "imu_sample", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_imu_sample_session_id", table_name="imu_sample")
    op.drop_table("imu_sample")
