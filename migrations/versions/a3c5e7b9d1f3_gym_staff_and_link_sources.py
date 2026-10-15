"""gym_staff; coach_assignment.source_gym_id / granted_by (ADR-052)

Revision ID: a3c5e7b9d1f3
Revises: f1a3c5e7b9d1
Create Date: 2026-10-14

A gym's staff, with a role at that gym (owner, manager, head coach, coach),
becomes one list. What there was is carried over, active:
- a gym manager with an account → the gym's owner (its first manager) or a
  manager;
- a coach whose profile names a gym, or with a coach membership there → coach
  (the membership row is marked left: the staff list replaces it).
Coach links gain where they came from and who made them; existing links have
neither.

Idempotent guards, matching the other migrations here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7b9d1f3"
down_revision: str | Sequence[str] | None = "f1a3c5e7b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "gym_staff" not in insp.get_table_names():
        op.create_table(
            "gym_staff",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("gym_id", sa.Uuid(), sa.ForeignKey("gym.id"), nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("coach_id", sa.Uuid(), sa.ForeignKey("coach.id"), nullable=True),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=12), nullable=False),
            sa.Column("invited_by", sa.Uuid(), nullable=True),
            sa.Column("note", sa.String(length=300), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
        for col in ("gym_id", "user_id", "coach_id"):
            op.create_index(f"ix_gym_staff_{col}", "gym_staff", [col])
        _carry_over()
    cols = {c["name"] for c in insp.get_columns("coach_assignment")}
    with op.batch_alter_table("coach_assignment") as batch:
        if "source_gym_id" not in cols:
            batch.add_column(sa.Column("source_gym_id", sa.Uuid(), nullable=True))
        if "granted_by" not in cols:
            batch.add_column(sa.Column("granted_by", sa.Uuid(), nullable=True))


def _carry_over() -> None:
    now = "strftime('%Y-%m-%d %H:%M:%f', 'now')"
    # Managers with an account: the gym's first one owns it.
    op.execute(
        f"""
        INSERT INTO gym_staff (gym_id, user_id, role, status, note, created_at, started_at)
        SELECT gm.gym_id, u.id,
               CASE WHEN gm.created_at = (SELECT min(g2.created_at) FROM gym_manager g2
                                          WHERE g2.gym_id = gm.gym_id)
                    THEN 'owner' ELSE 'manager' END,
               'active', 'Carried over (ADR-052)', {now}, gm.created_at
          FROM gym_manager gm JOIN user u ON u.profile_id = gm.id AND u.role = 'GYM_MANAGER'
        """
    )
    # Coaches: a profile naming a gym, or a coach membership there.
    op.execute(
        f"""
        INSERT INTO gym_staff (gym_id, user_id, coach_id, role, status, note, created_at, started_at)
        SELECT DISTINCT x.gym_id,
               (SELECT u.id FROM user u WHERE u.profile_id = x.coach_id AND u.role = 'COACH'),
               x.coach_id, 'coach', 'active', 'Carried over (ADR-052)', {now}, {now}
          FROM (SELECT c.gym_id AS gym_id, c.id AS coach_id FROM coach c
                 WHERE c.gym_id IS NOT NULL
                UNION
                SELECT m.gym_id, m.member_id FROM gym_membership m
                 WHERE m.member_type = 'coach' AND m.status IN ('active', 'trial')
                   AND m.member_id IN (SELECT id FROM coach)) x
        """
    )
    op.execute(
        """
        UPDATE gym_membership SET status = 'left', left_on = date('now'),
               status_note = 'Now on the gym''s staff list (ADR-052)'
         WHERE member_type = 'coach' AND status IN ('active', 'trial')
        """
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("coach_assignment")}
    with op.batch_alter_table("coach_assignment") as batch:
        for col in ("source_gym_id", "granted_by"):
            if col in cols:
                batch.drop_column(col)
    if "gym_staff" in insp.get_table_names():
        op.drop_table("gym_staff")
