"""add session baseline hrv columns

Revision ID: bcaa63d4ff90
Revises: 1f0501f1da74
Create Date: 2026-05-06 16:12:52.673639

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-emitted columns reference sqlmodel.sql.sqltypes.*


# revision identifiers, used by Alembic.
revision: str = 'bcaa63d4ff90'
down_revision: Union[str, Sequence[str], None] = '1f0501f1da74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("baseline_rmssd_ms", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("baseline_sdnn_ms", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("baseline_mean_hr_bpm", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("baseline_recorded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_column("baseline_recorded_at")
        batch_op.drop_column("baseline_mean_hr_bpm")
        batch_op.drop_column("baseline_sdnn_ms")
        batch_op.drop_column("baseline_rmssd_ms")
