"""add pose_backend to session

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "session",
        sa.Column("pose_backend", sa.String(), server_default="mediapipe", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("session", "pose_backend")
