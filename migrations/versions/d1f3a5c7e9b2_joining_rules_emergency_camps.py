"""gym rules and join code; membership rules acceptance; emergency contact;
a camp's bout (ADR-055)

Revision ID: d1f3a5c7e9b2
Revises: c5e7a9b1d3f5
Create Date: 2026-10-15

Joining a gym: a code a fighter asks to join with (the gym approves — a new
"applied" membership status, a string, so no column change), the gym's rules
they accept (and which version), and an emergency contact on the fighter's
profile. A fight camp can name its bout.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1f3a5c7e9b2"
down_revision: str | Sequence[str] | None = "c5e7a9b1d3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADD = {
    "gym": [
        ("rules", sa.Text()),
        ("rules_version", sa.Integer()),
        ("join_code", sa.String(length=16)),
    ],
    "gym_membership": [
        ("rules_version", sa.Integer()),
        ("rules_accepted_at", sa.DateTime()),
    ],
    "fighter": [
        ("emergency_contact_name", sa.String(length=120)),
        ("emergency_contact_phone", sa.String(length=40)),
        ("emergency_contact_relation", sa.String(length=60)),
    ],
    "squad": [("bout_id", sa.Uuid())],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, columns in ADD.items():
        have = {c["name"] for c in insp.get_columns(table)}
        missing = [(n, t) for n, t in columns if n not in have]
        if not missing:
            continue
        with op.batch_alter_table(table) as batch:
            for name, kind in missing:
                default = sa.text("0") if name == "rules_version" and table == "gym" else None
                batch.add_column(
                    sa.Column(name, kind, nullable=default is None, server_default=default)
                )
            if table == "gym" and "join_code" in {n for n, _ in missing}:
                batch.create_index("ix_gym_join_code", ["join_code"], unique=True)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, columns in ADD.items():
        have = {c["name"] for c in insp.get_columns(table)}
        present = [n for n, _ in columns if n in have]
        if not present:
            continue
        # Rebuilding gym_membership re-reads its status column, whose stored default
        # SQLite won't take back as written: give it explicitly.
        keep = (
            [sa.Column("status", sa.String(20), nullable=False, server_default="active")]
            if table == "gym_membership"
            else []
        )
        with op.batch_alter_table(table, reflect_args=keep) as batch:
            if table == "gym" and "join_code" in present:
                batch.drop_index("ix_gym_join_code")
            for name in present:
                batch.drop_column(name)
