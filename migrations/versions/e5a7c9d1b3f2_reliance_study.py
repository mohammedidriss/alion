"""reliance study — reviewers, frozen advisories, claims, decisions, trust (ADR-026)

Revision ID: e5a7c9d1b3f2
Revises: d2e8b4c6f9a1
Create Date: 2026-10-13

The appropriate-reliance study: researcher-enrolled reviewers (a study code per
account), adjudicated advisory snapshots split into claims with their evidence,
evidence opens, follow/adjust/reject decisions with timing and position, and
trust/distrust check-ins at three time points. Adapted from the Proposal V2 test
build's schema.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a7c9d1b3f2"
down_revision: str | Sequence[str] | None = "d2e8b4c6f9a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "study_trust_survey",
    "study_reliance_trial",
    "study_trace_open",
    "study_advice_claim",
    "study_advice_snapshot",
    "study_reviewer",
)


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())

    if "study_reviewer" not in have:
        op.create_table(
            "study_reviewer",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False, unique=True),
            sa.Column("reviewer_code", sa.String(length=20), nullable=False, unique=True),
            sa.Column("enrolled_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_study_reviewer_user_id", "study_reviewer", ["user_id"])
        op.create_index("ix_study_reviewer_reviewer_code", "study_reviewer", ["reviewer_code"])

    if "study_advice_snapshot" not in have:
        op.create_table(
            "study_advice_snapshot",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session.id"), nullable=False),
            sa.Column("payload_mode", sa.String(length=10), nullable=False),
            sa.Column("model_id", sa.String(length=160), nullable=False),
            sa.Column("prompt_version", sa.String(length=40), nullable=False),
            sa.Column("input_json", sa.String(), nullable=False),
            sa.Column("advice_json", sa.String(), nullable=False),
            sa.Column("input_sha256", sa.String(length=64), nullable=False),
            sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
            sa.Column("output_sha256", sa.String(length=64), nullable=False),
            sa.Column("correctness", sa.String(), nullable=False),
            sa.Column("adjudication_note", sa.String(), nullable=False),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_study_advice_snapshot_session_id", "study_advice_snapshot", ["session_id"]
        )
        op.create_index(
            "ix_study_advice_snapshot_input_sha256", "study_advice_snapshot", ["input_sha256"]
        )

    if "study_advice_claim" not in have:
        op.create_table(
            "study_advice_claim",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "snapshot_id", sa.Uuid(), sa.ForeignKey("study_advice_snapshot.id"), nullable=False
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("claim_text", sa.String(), nullable=False),
            sa.Column("evidence_json", sa.String(), nullable=False),
            sa.Column("source_stream", sa.String(length=40), nullable=False),
            sa.Column("source_start_ms", sa.Float(), nullable=True),
            sa.Column("source_end_ms", sa.Float(), nullable=True),
            sa.Column("evidence_quality", sa.String(length=40), nullable=False),
            sa.UniqueConstraint("snapshot_id", "ordinal"),
        )
        op.create_index("ix_study_advice_claim_snapshot_id", "study_advice_claim", ["snapshot_id"])

    if "study_trace_open" not in have:
        op.create_table(
            "study_trace_open",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "claim_id", sa.Uuid(), sa.ForeignKey("study_advice_claim.id"), nullable=False
            ),
            sa.Column("reviewer_code", sa.String(length=20), nullable=False),
            sa.Column("opened_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("claim_id", "reviewer_code"),
        )
        op.create_index("ix_study_trace_open_claim_id", "study_trace_open", ["claim_id"])
        op.create_index("ix_study_trace_open_reviewer_code", "study_trace_open", ["reviewer_code"])

    if "study_reliance_trial" not in have:
        op.create_table(
            "study_reliance_trial",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "snapshot_id", sa.Uuid(), sa.ForeignKey("study_advice_snapshot.id"), nullable=False
            ),
            sa.Column("reviewer_code", sa.String(length=20), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("decision", sa.String(), nullable=False),
            sa.Column("response_ms", sa.Integer(), nullable=False),
            sa.Column("rationale", sa.String(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("snapshot_id", "reviewer_code"),
        )
        op.create_index(
            "ix_study_reliance_trial_snapshot_id", "study_reliance_trial", ["snapshot_id"]
        )
        op.create_index(
            "ix_study_reliance_trial_reviewer_code", "study_reliance_trial", ["reviewer_code"]
        )

    if "study_trust_survey" not in have:
        op.create_table(
            "study_trust_survey",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("reviewer_code", sa.String(length=20), nullable=False),
            sa.Column("timepoint", sa.String(), nullable=False),
            sa.Column("after_trials", sa.Integer(), nullable=False),
            sa.Column("item_scores_json", sa.String(), nullable=False),
            sa.Column("trust_score", sa.Float(), nullable=False),
            sa.Column("distrust_score", sa.Float(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("reviewer_code", "timepoint"),
        )
        op.create_index(
            "ix_study_trust_survey_reviewer_code", "study_trust_survey", ["reviewer_code"]
        )


def downgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    for table in _TABLES:
        if table in have:
            op.drop_table(table)
