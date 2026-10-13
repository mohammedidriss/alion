"""access_log — medical-record access, who/when/which fighter (ADR-017)

Revision ID: c7f1a9e3b5d2
Revises: b4d8e2f6a1c3
Create Date: 2026-10-13

Every read or change of a fighter's medical data, and every refused attempt:
the account, its role, the fighter, the route, read/write, allowed — never the
content.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7f1a9e3b5d2"
down_revision: str | Sequence[str] | None = "b4d8e2f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "access_log" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "access_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("fighter_id", sa.Uuid(), nullable=False),
        sa.Column("resource", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
    )
    for col in ("at", "user_id", "fighter_id"):
        op.create_index(f"ix_access_log_{col}", "access_log", [col])


def downgrade() -> None:
    op.drop_table("access_log")
