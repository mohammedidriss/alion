"""A physician's own page (ADR-046): the fighters who chose them.

GET /physicians/me/fighters
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, require_viewer
from api.deps import db_session
from api.routes.auth import require_current_user
from store import Fighter, PhysicianAssignmentRow

router = APIRouter(
    prefix="/physicians", tags=["physicians"], dependencies=[Depends(require_current_user)]
)


class MyFighter(BaseModel):
    fighter_id: UUID
    name: str
    photo_path: str | None
    since: datetime


@router.get("/me/fighters", response_model=list[MyFighter])
def my_fighters(
    viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> list[MyFighter]:
    rows = db.exec(
        select(PhysicianAssignmentRow).where(
            PhysicianAssignmentRow.physician_id == viewer.user.id,
            col(PhysicianAssignmentRow.ended_at).is_(None),
        )
    ).all()
    out = []
    for r in rows:
        f = db.get(Fighter, r.fighter_id)
        if f is not None:
            out.append(
                MyFighter(fighter_id=f.id, name=f.name, photo_path=f.photo_path, since=r.started_at)
            )
    return sorted(out, key=lambda x: x.name.lower())
