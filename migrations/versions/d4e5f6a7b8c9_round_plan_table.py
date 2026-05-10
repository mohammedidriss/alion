"""round_plan table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "round_plan" not in insp.get_table_names():
        op.create_table(
            "round_plan",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=60), nullable=False),
            sa.Column("round_count", sa.Integer(), nullable=False),
            sa.Column("round_duration_s", sa.Integer(), nullable=False),
            sa.Column("rest_duration_s", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )


def downgrade() -> None:
    op.drop_table("round_plan")
