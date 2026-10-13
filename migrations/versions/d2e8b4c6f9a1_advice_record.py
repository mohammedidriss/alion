"""advice_record — every AI advisory, its provenance and safety outcome (ADR-018)

Revision ID: d2e8b4c6f9a1
Revises: c7f1a9e3b5d2
Create Date: 2026-10-13

One row per piece of advice generated: kind, session/fighter, what produced it
(model, prompt version and hash, input hash, platform version), the output and
its hash, whether it was shown, withheld by the safety check (and the terms that
tripped it) or failed, who asked, and whether it is locked as a study stimulus.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e8b4c6f9a1"
down_revision: str | Sequence[str] | None = "c7f1a9e3b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "advice_record" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "advice_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("fighter_id", sa.Uuid(), nullable=True),
        sa.Column("payload_mode", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("blocked_terms", sa.String(), nullable=False),
        sa.Column("output_json", sa.String(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column("platform_version", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
    )
    for col in ("created_at", "session_id", "fighter_id"):
        op.create_index(f"ix_advice_record_{col}", "advice_record", [col])


def downgrade() -> None:
    op.drop_table("advice_record")
