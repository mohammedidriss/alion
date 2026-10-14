"""rest_hr_sample, card_feedback, pupil_reading (ADR-041, ADR-043, ADR-044)

Revision ID: b3d5f7a9c1e4
Revises: a1c3e5f7b9d2
Create Date: 2026-10-14

From the RingsideIQ review board: heartbeats during the rest between rounds
(heart-rate recovery), what coaches do with the rest cards, and pupillometer
readings as entered.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d5f7a9c1e4"
down_revision: str | Sequence[str] | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "rest_hr_sample" not in have:
        op.create_table(
            "rest_hr_sample",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=False),
            sa.Column("pause_started_ms", sa.Float(), nullable=False),
            sa.Column("at_ms", sa.Float(), nullable=False),
            sa.Column("rest_ms", sa.Float(), nullable=False),
            sa.Column("rr_ms", sa.Float(), nullable=False),
            sa.Column("hr_bpm", sa.Float(), nullable=False),
        )
        op.create_index("ix_rest_hr_sample_session_id", "rest_hr_sample", ["session_id"])
    if "card_feedback" not in have:
        op.create_table(
            "card_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=False),
            sa.Column("after_round", sa.Integer(), nullable=False),
            sa.Column("slot", sa.String(length=20), nullable=False),
            sa.Column("action", sa.String(length=20), nullable=False),
            sa.Column("headline", sa.String(length=200), nullable=True),
            sa.Column("fact_ids", sa.String(), nullable=False),
            sa.Column("facts_sha256", sa.String(length=64), nullable=True),
            sa.Column("note", sa.String(length=1000), nullable=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_card_feedback_session_id", "card_feedback", ["session_id"])
        op.create_index("ix_card_feedback_user_id", "card_feedback", ["user_id"])
    if "pupil_reading" not in have:
        op.create_table(
            "pupil_reading",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=True),
            sa.Column("taken_at", sa.DateTime(), nullable=False),
            sa.Column("eye", sa.String(length=5), nullable=False),
            sa.Column("npi", sa.Float(), nullable=True),
            sa.Column("size_mm", sa.Float(), nullable=True),
            sa.Column("device", sa.String(length=80), nullable=True),
            sa.Column("light_lux", sa.Float(), nullable=True),
            sa.Column("context", sa.String(length=200), nullable=True),
            sa.Column("entered_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pupil_reading_fighter_id", "pupil_reading", ["fighter_id"])


def downgrade() -> None:
    have = _tables()
    for t in ("pupil_reading", "card_feedback", "rest_hr_sample"):
        if t in have:
            op.drop_table(t)
