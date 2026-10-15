"""squad, squad_member, squad_staff; session.gym_id / squad_id (ADR-053)

Revision ID: c5e7a9b1d3f5
Revises: a3c5e7b9d1f3
Create Date: 2026-10-15

Squads within a gym — competition teams, classes, fight camps — with their
fighters (one squad marked a fighter's main one) and their coaches. A session
records the gym and squad it was trained with; existing sessions have neither.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7a9b1d3f5"
down_revision: str | Sequence[str] | None = "a3c5e7b9d1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = insp.get_table_names()
    if "squad" not in tables:
        op.create_table(
            "squad",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("gym_id", sa.Uuid(), sa.ForeignKey("gym.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("level", sa.String(length=80), nullable=True),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("starts_on", sa.Date(), nullable=True),
            sa.Column("ends_on", sa.Date(), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_squad_gym_id", "squad", ["gym_id"])
    if "squad_member" not in tables:
        op.create_table(
            "squad_member",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("squad_id", sa.Uuid(), sa.ForeignKey("squad.id"), nullable=False),
            sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
            sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("joined_on", sa.Date(), nullable=False),
            sa.Column("left_on", sa.Date(), nullable=True),
            sa.Column("added_by", sa.Uuid(), nullable=True),
        )
        op.create_index("ix_squad_member_squad_id", "squad_member", ["squad_id"])
        op.create_index("ix_squad_member_fighter_id", "squad_member", ["fighter_id"])
    if "squad_staff" not in tables:
        op.create_table(
            "squad_staff",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("squad_id", sa.Uuid(), sa.ForeignKey("squad.id"), nullable=False),
            sa.Column("coach_id", sa.Uuid(), sa.ForeignKey("coach.id"), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("started_on", sa.Date(), nullable=False),
            sa.Column("ended_on", sa.Date(), nullable=True),
            sa.Column("added_by", sa.Uuid(), nullable=True),
        )
        op.create_index("ix_squad_staff_squad_id", "squad_staff", ["squad_id"])
        op.create_index("ix_squad_staff_coach_id", "squad_staff", ["coach_id"])
    cols = {c["name"] for c in insp.get_columns("session")}
    with op.batch_alter_table("session") as batch:
        for col in ("gym_id", "squad_id"):
            if col not in cols:
                batch.add_column(sa.Column(col, sa.Uuid(), nullable=True))
                batch.create_index(f"ix_session_{col}", [col])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("session")}
    with op.batch_alter_table("session") as batch:
        for col in ("gym_id", "squad_id"):
            if col in cols:
                batch.drop_index(f"ix_session_{col}")
                batch.drop_column(col)
    for table in ("squad_staff", "squad_member", "squad"):
        if table in insp.get_table_names():
            op.drop_table(table)
