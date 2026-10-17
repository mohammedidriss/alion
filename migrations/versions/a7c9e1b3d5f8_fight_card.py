"""bout: the fight card — type, belts, event, weight, weigh-ins, officials (ADR-069)

Revision ID: a7c9e1b3d5f8
Revises: f5c7e9b1d3a6
Create Date: 2026-10-17

What a broadcast shows about a fight, alongside the two fighters' tale of the
tape (which stays on their profiles): professional title / non-title, amateur,
exhibition or sparring; the belts on the line (WBA, WBC, IBF, WBO, The Ring, …);
the event, arena and city; the weight class or catchweight limit and each
corner's official weigh-in; the referee and judges; the promoter and broadcaster.
Plus removed_at / removed_by: a deleted fight is hidden, its recordings kept
(ADR-056).

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1b3d5f8"
down_revision: str | Sequence[str] | None = "f5c7e9b1d3a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("fight_type", sa.String(), "'pro'"),
    ("titles", sa.JSON(), "'[]'"),
    ("event_name", sa.String(length=120), None),
    ("city", sa.String(length=80), None),
    ("country", sa.String(length=80), None),
    ("weight_class", sa.String(length=40), None),
    ("weight_limit_kg", sa.Float(), None),
    ("red_weigh_in_kg", sa.Float(), None),
    ("blue_weigh_in_kg", sa.Float(), None),
    ("referee", sa.String(length=120), None),
    ("judges", sa.JSON(), "'[]'"),
    ("promoter", sa.String(length=120), None),
    ("broadcaster", sa.String(length=120), None),
    ("removed_at", sa.DateTime(), None),
    ("removed_by", sa.Uuid(), None),
)


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("bout")}
    missing = [c for c in COLUMNS if c[0] not in cols]
    if missing:
        with op.batch_alter_table("bout") as batch:
            for name, kind, default in missing:
                batch.add_column(
                    sa.Column(
                        name,
                        kind,
                        nullable=default is None,
                        server_default=sa.text(default) if default else None,
                    )
                )


def downgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("bout")}
    present = [name for name, _, _ in COLUMNS if name in cols]
    if present:
        with op.batch_alter_table("bout") as batch:
            for name in present:
                batch.drop_column(name)
