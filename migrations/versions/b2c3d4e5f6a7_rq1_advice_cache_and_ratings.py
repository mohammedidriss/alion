"""rq1 advice cache + rater scores

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    def has_index(table: str, name: str) -> bool:
        try:
            return any(ix["name"] == name for ix in insp.get_indexes(table))
        except Exception:
            return False

    if "coach_advice_cache" not in existing:
        op.create_table(
            "coach_advice_cache",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("payload_mode", sa.String(length=10), nullable=False),
            sa.Column("prompt_version", sa.String(length=20), nullable=False, server_default="v1"),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("action_items_json", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        )
    if not has_index("coach_advice_cache", "ix_coach_advice_cache_session_id"):
        op.create_index(
            "ix_coach_advice_cache_session_id",
            "coach_advice_cache",
            ["session_id"],
            unique=False,
        )
    if not has_index("coach_advice_cache", "ix_coach_advice_cache_lookup"):
        op.create_index(
            "ix_coach_advice_cache_lookup",
            "coach_advice_cache",
            ["session_id", "payload_mode", "prompt_version"],
            unique=True,
        )

    if "rq1_rating" not in existing:
        op.create_table(
            "rq1_rating",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), nullable=False, index=True),
            sa.Column("payload_mode", sa.String(length=10), nullable=False),
            sa.Column("rater_id", sa.String(length=80), nullable=False, index=True),
            sa.Column("criterion", sa.String(length=40), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        )
    if not has_index("rq1_rating", "ix_rq1_rating_session_id"):
        op.create_index("ix_rq1_rating_session_id", "rq1_rating", ["session_id"], unique=False)
    if not has_index("rq1_rating", "ix_rq1_rating_rater_id"):
        op.create_index("ix_rq1_rating_rater_id", "rq1_rating", ["rater_id"], unique=False)
    if not has_index("rq1_rating", "ix_rq1_rating_unique"):
        op.create_index(
            "ix_rq1_rating_unique",
            "rq1_rating",
            ["session_id", "payload_mode", "rater_id", "criterion"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_rq1_rating_unique", table_name="rq1_rating")
    op.drop_index("ix_rq1_rating_rater_id", table_name="rq1_rating")
    op.drop_index("ix_rq1_rating_session_id", table_name="rq1_rating")
    op.drop_table("rq1_rating")
    op.drop_index("ix_coach_advice_cache_lookup", table_name="coach_advice_cache")
    op.drop_index("ix_coach_advice_cache_session_id", table_name="coach_advice_cache")
    op.drop_table("coach_advice_cache")
