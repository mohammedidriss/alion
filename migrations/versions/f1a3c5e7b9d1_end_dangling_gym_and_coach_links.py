"""end gym memberships and coach links whose person no longer exists (ADR-050)

Revision ID: f1a3c5e7b9d1
Revises: e9b1d3f5a7c9
Create Date: 2026-10-14

A membership whose fighter or coach profile is gone is marked left, and a coach
link whose coach or fighter is gone is ended — nothing is deleted, and nothing
that points at a real profile is touched. Running it again changes nothing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f1a3c5e7b9d1"
down_revision: str | Sequence[str] | None = "e9b1d3f5a7c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE gym_membership
           SET status = 'left', left_on = date('now'),
               status_note = 'Ended: the profile no longer exists'
         WHERE status NOT IN ('left', 'declined')
           AND ((member_type = 'fighter' AND member_id NOT IN (SELECT id FROM fighter))
             OR (member_type = 'coach' AND member_id NOT IN (SELECT id FROM coach)))
        """
    )
    op.execute(
        """
        UPDATE coach_assignment
           SET ended_on = date('now')
         WHERE ended_on IS NULL
           AND (coach_id NOT IN (SELECT id FROM coach)
             OR fighter_id NOT IN (SELECT id FROM fighter))
        """
    )


def downgrade() -> None:
    """Nothing to undo: the rows still exist, and their people don't."""
