"""physician_assignment; coach_assignment.health_access (ADR-046)

Revision ID: d7f9b1c3e5a7
Revises: c5e7a9b1d3f6
Create Date: 2026-10-14

A fighter chooses their physicians; a coach sees the fighter's health notes only
when the fighter allows it. Coaches already assigned keep the access they had
(health_access true); new assignments start without it.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f9b1c3e5a7"
down_revision: str | Sequence[str] | None = "c5e7a9b1d3f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("coach_assignment")}
    if "health_access" not in cols:
        with op.batch_alter_table("coach_assignment") as batch:
            batch.add_column(
                sa.Column("health_access", sa.Boolean(), nullable=False, server_default=sa.true())
            )
    if "physician_assignment" not in insp.get_table_names():
        op.create_table(
            "physician_assignment",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
            sa.Column("physician_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_physician_assignment_fighter_id", "physician_assignment", ["fighter_id"]
        )
        op.create_index(
            "ix_physician_assignment_physician_id", "physician_assignment", ["physician_id"]
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "physician_assignment" in insp.get_table_names():
        op.drop_table("physician_assignment")
    cols = {c["name"] for c in insp.get_columns("coach_assignment")}
    if "health_access" in cols:
        with op.batch_alter_table("coach_assignment") as batch:
            batch.drop_column("health_access")
