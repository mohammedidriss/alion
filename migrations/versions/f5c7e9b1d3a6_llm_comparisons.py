"""llm_comparison, llm_trial_result, llm_rating (ADR-058)

Revision ID: f5c7e9b1d3a6
Revises: e3a5c7e9b1d4
Create Date: 2026-10-15

Language-model comparisons are saved: the models (each under a blind code), the
sessions and repeats, every trial's result, and researchers' blind ratings.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5c7e9b1d3a6"
down_revision: str | Sequence[str] | None = "e3a5c7e9b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "llm_comparison" not in tables:
        op.create_table(
            "llm_comparison",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=False),
            sa.Column("models", sa.Text(), nullable=False),
            sa.Column("session_ids", sa.Text(), nullable=False),
            sa.Column("repeats", sa.Integer(), nullable=False),
            sa.Column("total", sa.Integer(), nullable=False),
            sa.Column("step", sa.String(length=200), nullable=True),
            sa.Column("revealed_at", sa.DateTime(), nullable=True),
        )
    if "llm_trial_result" not in tables:
        op.create_table(
            "llm_trial_result",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "comparison_id", sa.Uuid(), sa.ForeignKey("llm_comparison.id"), nullable=False
            ),
            sa.Column("code", sa.String(length=4), nullable=False),
            sa.Column("choice", sa.String(length=12), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("session_id", sa.Uuid(), nullable=False),
            sa.Column("after_round", sa.Integer(), nullable=False),
            sa.Column("repeat", sa.Integer(), nullable=False),
            sa.Column("seconds", sa.Float(), nullable=True),
            sa.Column("answered", sa.Boolean(), nullable=False),
            sa.Column("in_time", sa.Boolean(), nullable=False),
            sa.Column("written", sa.Integer(), nullable=False),
            sa.Column("passed", sa.Integer(), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_llm_trial_result_comparison_id", "llm_trial_result", ["comparison_id"])
    if "llm_rating" not in tables:
        op.create_table(
            "llm_rating",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "comparison_id", sa.Uuid(), sa.ForeignKey("llm_comparison.id"), nullable=False
            ),
            sa.Column(
                "trial_id", sa.Integer(), sa.ForeignKey("llm_trial_result.id"), nullable=False
            ),
            sa.Column("rater_id", sa.Uuid(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("blind", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_llm_rating_comparison_id", "llm_rating", ["comparison_id"])
        op.create_index("ix_llm_rating_trial_id", "llm_rating", ["trial_id"])


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    for table in ("llm_rating", "llm_trial_result", "llm_comparison"):
        if table in tables:
            op.drop_table(table)
