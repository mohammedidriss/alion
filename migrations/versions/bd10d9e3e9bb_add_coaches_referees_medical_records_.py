"""add coaches, referees, medical records, photos

Revision ID: bd10d9e3e9bb
Revises: bcaa63d4ff90
Create Date: 2026-05-06 17:19:29.155090

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bd10d9e3e9bb"
down_revision: str | Sequence[str] | None = "bcaa63d4ff90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fighter", schema=None) as batch_op:
        batch_op.add_column(sa.Column("photo_path", sa.String(), nullable=True))

    op.create_table(
        "coach",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("gym", sa.String(length=120), nullable=True),
        sa.Column("specialties", sa.String(length=200), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("bio", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "referee",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("license_number", sa.String(length=80), nullable=True),
        sa.Column("sanctioning_body", sa.String(length=120), nullable=True),
        sa.Column("license_expiry", sa.Date(), nullable=True),
        sa.Column("bio", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "medical_record",
        sa.Column(
            "fighter_id",
            sa.Uuid(),
            sa.ForeignKey("fighter.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("blood_type", sa.String(length=4), nullable=True),
        sa.Column("last_clearance_date", sa.Date(), nullable=True),
        sa.Column("clearing_physician", sa.String(length=120), nullable=True),
        sa.Column("primary_physician", sa.String(length=120), nullable=True),
        sa.Column("primary_physician_phone", sa.String(length=40), nullable=True),
        sa.Column("emergency_contact_name", sa.String(length=120), nullable=True),
        sa.Column("emergency_contact_relation", sa.String(length=80), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(length=40), nullable=True),
        sa.Column("insurance_provider", sa.String(length=120), nullable=True),
        sa.Column("insurance_policy", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    severity_enum = sa.Enum("MILD", "MODERATE", "SEVERE", "ANAPHYLACTIC", name="allergyseverity")
    op.create_table(
        "allergy",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("substance", sa.String(length=120), nullable=False),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_allergy_fighter_id", "allergy", ["fighter_id"])

    op.create_table(
        "medication",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("dose", sa.String(length=80), nullable=True),
        sa.Column("frequency", sa.String(length=80), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("prescribed_by", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_medication_fighter_id", "medication", ["fighter_id"])

    status_enum = sa.Enum("ACTIVE", "MANAGED", "RECOVERED", name="conditionstatus")
    op.create_table(
        "medical_condition",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("fighter_id", sa.Uuid(), sa.ForeignKey("fighter.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("diagnosed_on", sa.Date(), nullable=True),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_medical_condition_fighter_id", "medical_condition", ["fighter_id"])


def downgrade() -> None:
    op.drop_index("ix_medical_condition_fighter_id", table_name="medical_condition")
    op.drop_table("medical_condition")
    op.drop_index("ix_medication_fighter_id", table_name="medication")
    op.drop_table("medication")
    op.drop_index("ix_allergy_fighter_id", table_name="allergy")
    op.drop_table("allergy")
    op.drop_table("medical_record")
    op.drop_table("referee")
    op.drop_table("coach")
    with op.batch_alter_table("fighter", schema=None) as batch_op:
        batch_op.drop_column("photo_path")
    sa.Enum(name="conditionstatus").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="allergyseverity").drop(op.get_bind(), checkfirst=False)
