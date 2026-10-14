"""user.removed_at / removed_email / removed_by (ADR-048)

Revision ID: e9b1d3f5a7c9
Revises: d7f9b1c3e5a7
Create Date: 2026-10-14

An administrator removes an account instead of deleting its row: it can't sign
in, its email is free for a new account, and the person's profile, sessions and
records stay. The address it had is kept so the account can be restored.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9b1d3f5a7c9"
down_revision: str | Sequence[str] | None = "d7f9b1c3e5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("removed_at", sa.DateTime()),
    ("removed_email", sa.String(length=200)),
    ("removed_by", sa.Uuid()),
)


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user")}
    missing = [(name, kind) for name, kind in COLUMNS if name not in cols]
    if missing:
        with op.batch_alter_table("user") as batch:
            for name, kind in missing:
                batch.add_column(sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("user")}
    present = [name for name, _ in COLUMNS if name in cols]
    if present:
        with op.batch_alter_table("user") as batch:
            for name in present:
                batch.drop_column(name)
