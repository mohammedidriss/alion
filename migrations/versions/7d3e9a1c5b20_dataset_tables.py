"""dataset, dataset_participant, dataset_take (ADR-013)

Revision ID: 7d3e9a1c5b20
Revises: 2f8a4b6c1d3e
Create Date: 2026-10-04

Datasets — a recording system separate from training sessions (ADR-013). These
tables only index the take folders under data/datasets/ and enforce consent; the
recorded data (video, IMU, HR, labels) lives in the files.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d3e9a1c5b20"
down_revision: str | Sequence[str] | None = "2f8a4b6c1d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "dataset" not in tables:
        op.create_table(
            "dataset",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("protocol", sa.String(length=60), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "dataset_participant" not in tables:
        op.create_table(
            "dataset_participant",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("dataset_id", sa.Uuid(), nullable=False),
            sa.Column("fighter_id", sa.Uuid(), nullable=False),
            sa.Column("consent", sa.String(), nullable=False),
            sa.Column("consent_date", sa.Date(), nullable=True),
            sa.Column("irb_ref", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"]),
            sa.ForeignKeyConstraint(["fighter_id"], ["fighter.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dataset_id", "fighter_id"),
        )
        op.create_index("ix_dataset_participant_dataset_id", "dataset_participant", ["dataset_id"])
        op.create_index("ix_dataset_participant_fighter_id", "dataset_participant", ["fighter_id"])

    if "dataset_take" not in tables:
        op.create_table(
            "dataset_take",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("dataset_id", sa.Uuid(), nullable=False),
            sa.Column("fighter_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Float(), nullable=False),
            sa.Column("notes", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"]),
            sa.ForeignKeyConstraint(["fighter_id"], ["fighter.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_dataset_take_dataset_id", "dataset_take", ["dataset_id"])
        op.create_index("ix_dataset_take_fighter_id", "dataset_take", ["fighter_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_take_fighter_id", table_name="dataset_take")
    op.drop_index("ix_dataset_take_dataset_id", table_name="dataset_take")
    op.drop_table("dataset_take")
    op.drop_index("ix_dataset_participant_fighter_id", table_name="dataset_participant")
    op.drop_index("ix_dataset_participant_dataset_id", table_name="dataset_participant")
    op.drop_table("dataset_participant")
    op.drop_table("dataset")
