"""add fighter team: bio, history, titles, sponsors, coach assignments

Revision ID: 61d4935702b2
Revises: 0092952195cf
Create Date: 2026-05-07 17:39:45.177615

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "61d4935702b2"
down_revision: str | Sequence[str] | None = "0092952195cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fighter", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bio", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("career_history", sa.String(), nullable=True))

    title_status_enum = sa.Enum("ACTIVE", "LOST", "VACATED", "RETIRED", name="titlestatus")
    op.create_table(
        "fighter_title",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("organization", sa.String(length=80), nullable=True),
        sa.Column("weight_class", sa.String(length=40), nullable=True),
        sa.Column("won_on", sa.Date(), nullable=True),
        sa.Column("lost_on", sa.Date(), nullable=True),
        sa.Column("status", title_status_enum, nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fighter_title_fighter_id", "fighter_title", ["fighter_id"])

    op.create_table(
        "fighter_sponsor",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("website", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fighter_sponsor_fighter_id", "fighter_sponsor", ["fighter_id"])

    coach_role_enum = sa.Enum(
        "HEAD_COACH",
        "STRIKING",
        "STRENGTH",
        "CONDITIONING",
        "NUTRITION",
        "CUTMAN",
        "MENTAL",
        "OTHER",
        name="coachrole",
    )
    op.create_table(
        "coach_assignment",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("coach_id", sa.Uuid(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("role", coach_role_enum, nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_coach_assignment_fighter_id", "coach_assignment", ["fighter_id"])
    op.create_index("ix_coach_assignment_coach_id", "coach_assignment", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_coach_assignment_coach_id", table_name="coach_assignment")
    op.drop_index("ix_coach_assignment_fighter_id", table_name="coach_assignment")
    op.drop_table("coach_assignment")
    op.drop_index("ix_fighter_sponsor_fighter_id", table_name="fighter_sponsor")
    op.drop_table("fighter_sponsor")
    op.drop_index("ix_fighter_title_fighter_id", table_name="fighter_title")
    op.drop_table("fighter_title")
    with op.batch_alter_table("fighter", schema=None) as batch_op:
        batch_op.drop_column("career_history")
        batch_op.drop_column("bio")
    sa.Enum(name="coachrole").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="titlestatus").drop(op.get_bind(), checkfirst=False)
