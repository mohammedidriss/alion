"""rq1_rater: the coaches a researcher chose to rate RQ1 advice (ADR-045)

Revision ID: c5e7a9b1d3f6
Revises: b3d5f7a9c1e4
Create Date: 2026-10-14

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7a9b1d3f6"
down_revision: str | Sequence[str] | None = "b3d5f7a9c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "rq1_rater" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "rq1_rater",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("enrolled_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_rq1_rater_user_id", "rq1_rater", ["user_id"], unique=True)


def downgrade() -> None:
    if "rq1_rater" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("rq1_rater")
