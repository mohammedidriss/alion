"""extend coach + referee fields

Revision ID: 0092952195cf
Revises: bd10d9e3e9bb
Create Date: 2026-05-06 19:25:39.390203

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092952195cf"
down_revision: str | Sequence[str] | None = "bd10d9e3e9bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    coaching_level_enum = sa.Enum("AMATEUR", "PROFESSIONAL", "BOTH", name="coachinglevel")
    cert_level_enum = sa.Enum(
        "LOCAL", "REGIONAL", "NATIONAL", "INTERNATIONAL", name="refereecertlevel"
    )

    with op.batch_alter_table("coach", schema=None) as batch_op:
        batch_op.add_column(sa.Column("dob", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("nationality", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("sex", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("coaching_level", coaching_level_enum, nullable=True))
        batch_op.add_column(sa.Column("certifications", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("license_number", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("license_expiry", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("languages", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("notable_fighters", sa.String(length=400), nullable=True))

    with op.batch_alter_table("referee", schema=None) as batch_op:
        batch_op.add_column(sa.Column("dob", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("nationality", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("sex", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("phone", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("certification_level", cert_level_enum, nullable=True))
        batch_op.add_column(sa.Column("years_officiating", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("languages", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("notable_bouts", sa.String(length=400), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("referee", schema=None) as batch_op:
        for col in [
            "notable_bouts",
            "languages",
            "years_officiating",
            "certification_level",
            "phone",
            "email",
            "sex",
            "nationality",
            "dob",
        ]:
            batch_op.drop_column(col)
    with op.batch_alter_table("coach", schema=None) as batch_op:
        for col in [
            "notable_fighters",
            "languages",
            "license_expiry",
            "license_number",
            "certifications",
            "coaching_level",
            "phone",
            "email",
            "sex",
            "nationality",
            "dob",
        ]:
            batch_op.drop_column(col)
    sa.Enum(name="refereecertlevel").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="coachinglevel").drop(op.get_bind(), checkfirst=False)
