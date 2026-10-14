"""data_request — privacy requests: export, delete, withdraw (ADR-033)

Revision ID: f7b9d1e3a5c7
Revises: e5a7c9d1b3f2
Create Date: 2026-10-14

A person asks for a copy of their data, its deletion, or to leave the research
datasets; an admin or a researcher closes the request with a note.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7b9d1e3a5c7"
down_revision: str | Sequence[str] | None = "e5a7c9d1b3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "data_request" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "data_request",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("handled_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("response", sa.String(length=2000), nullable=True),
    )
    op.create_index("ix_data_request_user_id", "data_request", ["user_id"])


def downgrade() -> None:
    if "data_request" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("data_request")
