"""add study_condition to session

Revision ID: 1ca85f671aa5
Revises: e5f6a7b8c9d0
Create Date: 2026-05-13 18:49:53.601347

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1ca85f671aa5"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add study_condition column to session table for RQ2 five-condition design."""
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("study_condition", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove study_condition column from session table."""
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_column("study_condition")
