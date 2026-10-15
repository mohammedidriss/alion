"""fighter.removed_at / removed_by; session.removed_at / removed_by (ADR-056)

Revision ID: e3a5c7e9b1d4
Revises: d1f3a5c7e9b2
Create Date: 2026-10-15

Recordings are never deleted: deleting a fighter profile or a session now hides
it, and keeps the recording and its heart-rate and wrist-sensor data.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a5c7e9b1d4"
down_revision: str | Sequence[str] | None = "d1f3a5c7e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("fighter", "session")
COLUMNS = (("removed_at", sa.DateTime()), ("removed_by", sa.Uuid()))


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table in TABLES:
        have = {c["name"] for c in insp.get_columns(table)}
        missing = [(n, t) for n, t in COLUMNS if n not in have]
        if missing:
            with op.batch_alter_table(table) as batch:
                for name, kind in missing:
                    batch.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table in TABLES:
        have = {c["name"] for c in insp.get_columns(table)}
        present = [n for n, _ in COLUMNS if n in have]
        if present:
            with op.batch_alter_table(table) as batch:
                for name in present:
                    batch.drop_column(name)
