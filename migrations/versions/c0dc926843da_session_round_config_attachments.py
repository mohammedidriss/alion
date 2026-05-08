"""session round config + attachments

Revision ID: c0dc926843da
Revises: 61d4935702b2
Create Date: 2026-05-08 13:25:24.122597

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0dc926843da"
down_revision: str | Sequence[str] | None = "61d4935702b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("round_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("round_duration_s", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rest_duration_s", sa.Integer(), nullable=True))

    kind_enum = sa.Enum("VIDEO", "IMAGE", "AUDIO", "DOCUMENT", "OTHER", name="attachmentkind")
    op.create_table(
        "session_attachment",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=400), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_session_attachment_session_id",
        "session_attachment",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_attachment_session_id", table_name="session_attachment")
    op.drop_table("session_attachment")
    sa.Enum(name="attachmentkind").drop(op.get_bind(), checkfirst=False)
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_column("rest_duration_s")
        batch_op.drop_column("round_duration_s")
        batch_op.drop_column("round_count")
