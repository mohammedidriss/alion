"""Squads (ADR-053): groups of fighters within a gym — a competition team, a class,
a fight camp — each with its own coaches.

GET  /gyms/{gym_id}/squads                      the gym's squads, with this week's numbers
POST /gyms/{gym_id}/squads                      create one
GET  /squads/{id}                               a squad, its fighters and its coaches
PATCH /squads/{id}                              change its name, kind, level, dates
POST /squads/{id}/archive                       close it: no access through it any more
POST /squads/{id}/members                       put a fighter on it {"fighter_id", "is_main"?}
PATCH /squads/{id}/members/{member_id}          {"is_main": true}: the fighter's main squad
POST /squads/{id}/members/{member_id}/end       take a fighter off it
POST /squads/{id}/staff                         add a coach {"coach_id", "role"?}
POST /squads/{id}/staff/{staff_id}/end          take a coach off it
GET  /fighters/{fighter_id}/squads              a fighter's squads
GET  /v2/my-squads                              the squads the signed-in coach coaches

The gym's owners, managers and head coaches run its squads. A squad's fighters
are the gym's accepted members; its coaches are the gym's coaching staff. A squad
coach sees the squad's fighters' training while both are on it and the squad is
open (not archived, not past its end date); health notes stay the fighter's to
share (ADR-046).
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api import access
from api.deps import db_session
from api.routes.auth import require_current_user
from store import Coach, Fighter, Gym, Squad, SquadKind, SquadMember, SquadStaff
from store import Session as SessionRow

router = APIRouter(tags=["squads"], dependencies=[Depends(require_current_user)])


class SquadIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: SquadKind = SquadKind.COMPETITION
    level: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None


class SquadPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: SquadKind | None = None
    level: str | None = None
    description: str | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None


class MemberIn(BaseModel):
    fighter_id: UUID
    is_main: bool = False


class MainIn(BaseModel):
    is_main: bool


class StaffIn(BaseModel):
    coach_id: UUID
    role: str = Field(default="coach", pattern="^(head_coach|coach)$")


class SquadMemberOut(BaseModel):
    id: int
    fighter_id: UUID
    name: str
    is_main: bool
    joined_on: dt.date
    left_on: dt.date | None


class SquadStaffOut(BaseModel):
    id: int
    coach_id: UUID
    name: str
    role: str
    started_on: dt.date
    ended_on: dt.date | None


class SquadOut(BaseModel):
    id: UUID
    gym_id: UUID
    gym_name: str
    name: str
    kind: str
    level: str | None
    description: str | None
    starts_on: dt.date | None
    ends_on: dt.date | None
    open: bool  # gives access today: not archived, not past its end date
    archived_at: dt.datetime | None
    fighters: int
    coaches: list[str]
    # This week, for those who may see the fighters' training (None otherwise):
    sessions_7d: int | None = None  # sessions trained with this squad
    trained_7d: int | None = None  # its fighters who trained at all
    members: list[SquadMemberOut] | None = None  # on the detail
    staff: list[SquadStaffOut] | None = None
    # On a fighter's list: their place on it.
    member_id: int | None = None
    is_main: bool | None = None


def _open(s: Squad) -> bool:
    return s.archived_at is None and (s.ends_on is None or s.ends_on >= dt.date.today())


def _members(db: DBSession, squad_id: UUID, *, current: bool = True) -> list[SquadMember]:
    q = select(SquadMember).where(SquadMember.squad_id == squad_id)
    if current:
        q = q.where(col(SquadMember.left_on).is_(None))
    return list(db.exec(q).all())


def _staff(db: DBSession, squad_id: UUID, *, current: bool = True) -> list[SquadStaff]:
    q = select(SquadStaff).where(SquadStaff.squad_id == squad_id)
    if current:
        q = q.where(col(SquadStaff.ended_on).is_(None))
    return list(db.exec(q).all())


def _name(db: DBSession, model: Any, id_: UUID) -> str:
    row = db.get(model, id_)
    return row.name if row else "?"


def _out(db: DBSession, s: Squad, viewer: access.Viewer, *, detail: bool = False) -> SquadOut:
    members = _members(db, s.id)
    staff = _staff(db, s.id)
    gym = db.get(Gym, s.gym_id)
    out = SquadOut(
        id=s.id,
        gym_id=s.gym_id,
        gym_name=gym.name if gym else "?",
        name=s.name,
        kind=s.kind,
        level=s.level,
        description=s.description,
        starts_on=s.starts_on,
        ends_on=s.ends_on,
        open=_open(s),
        archived_at=s.archived_at,
        fighters=len(members),
        coaches=sorted(_name(db, Coach, c.coach_id) for c in staff),
    )
    fighter_ids = {m.fighter_id for m in members}
    if fighter_ids and all(viewer.can(f, access.Level.TRAINING) for f in fighter_ids):
        since = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=7)
        recent = db.exec(
            select(SessionRow).where(
                col(SessionRow.fighter_id).in_(fighter_ids), SessionRow.started_at >= since
            )
        ).all()
        out.sessions_7d = sum(1 for r in recent if r.squad_id == s.id)
        out.trained_7d = len({r.fighter_id for r in recent})
    if detail:
        out.members = [
            SquadMemberOut(
                id=m.id or 0,
                fighter_id=m.fighter_id,
                name=_name(db, Fighter, m.fighter_id),
                is_main=m.is_main,
                joined_on=m.joined_on,
                left_on=m.left_on,
            )
            for m in sorted(members, key=lambda m: _name(db, Fighter, m.fighter_id).lower())
        ]
        out.staff = [
            SquadStaffOut(
                id=c.id or 0,
                coach_id=c.coach_id,
                name=_name(db, Coach, c.coach_id),
                role=c.role,
                started_on=c.started_on,
                ended_on=c.ended_on,
            )
            for c in sorted(staff, key=lambda c: (c.role != "head_coach", c.started_on))
        ]
    return out


def _squad(db: DBSession, squad_id: UUID) -> Squad:
    s = db.get(Squad, squad_id)
    if s is None:
        raise HTTPException(status_code=404, detail="squad not found")
    return s


def _runs(viewer: access.Viewer, gym_id: UUID) -> None:
    """The gym's owners, managers and head coaches run its squads."""
    if not (viewer.admin or gym_id in viewer.led_gyms):
        raise HTTPException(
            status_code=403, detail="Only this gym's owners, managers and head coaches"
        )


def _sees(viewer: access.Viewer, db: DBSession, s: Squad) -> None:
    """The gym's staff, and the squad's own fighters."""
    if viewer.admin or s.gym_id in viewer.led_gyms | viewer.coach_gyms:
        return
    if viewer.own_fighter is not None and viewer.own_fighter in {
        m.fighter_id for m in _members(db, s.id)
    }:
        return
    raise HTTPException(status_code=403, detail="No access to this squad")


@router.get("/gyms/{gym_id}/squads", response_model=list[SquadOut])
def list_squads(
    gym_id: UUID,
    archived: bool = False,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> list[SquadOut]:
    q = select(Squad).where(Squad.gym_id == gym_id)
    if not archived:
        q = q.where(col(Squad.archived_at).is_(None))
    rows = db.exec(q).all()
    return sorted((_out(db, s, viewer) for s in rows), key=lambda s: (not s.open, s.name.lower()))


@router.post("/gyms/{gym_id}/squads", response_model=SquadOut, status_code=status.HTTP_201_CREATED)
def create_squad(
    gym_id: UUID,
    body: SquadIn,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    if db.get(Gym, gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    _runs(viewer, gym_id)
    if body.starts_on and body.ends_on and body.ends_on < body.starts_on:
        raise HTTPException(status_code=422, detail="It ends before it starts")
    s = Squad(gym_id=gym_id, created_by=viewer.user.id, **body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(db, s, viewer, detail=True)


@router.get("/squads/{squad_id}", response_model=SquadOut)
def get_squad(
    squad_id: UUID,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    s = _squad(db, squad_id)
    _sees(viewer, db, s)
    return _out(db, s, viewer, detail=True)


@router.patch("/squads/{squad_id}", response_model=SquadOut)
def update_squad(
    squad_id: UUID,
    body: SquadPatch,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    s = _squad(db, squad_id)
    _runs(viewer, s.gym_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    if s.starts_on and s.ends_on and s.ends_on < s.starts_on:
        raise HTTPException(status_code=422, detail="It ends before it starts")
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(db, s, viewer, detail=True)


@router.post("/squads/{squad_id}/archive", response_model=SquadOut)
def archive_squad(
    squad_id: UUID,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    """Close the squad: its coaches' access through it ends; nothing is deleted."""
    s = _squad(db, squad_id)
    _runs(viewer, s.gym_id)
    s.archived_at = dt.datetime.now(dt.UTC)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(db, s, viewer, detail=True)


def _set_main(db: DBSession, member: SquadMember) -> None:
    """One main squad per fighter."""
    for other in db.exec(
        select(SquadMember).where(
            SquadMember.fighter_id == member.fighter_id,
            col(SquadMember.is_main),
            SquadMember.id != member.id,
        )
    ).all():
        other.is_main = False
        db.add(other)
    member.is_main = True


@router.post(
    "/squads/{squad_id}/members", response_model=SquadOut, status_code=status.HTTP_201_CREATED
)
def add_member(
    squad_id: UUID,
    body: MemberIn,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    s = _squad(db, squad_id)
    _runs(viewer, s.gym_id)
    if not _open(s):
        raise HTTPException(status_code=409, detail="This squad is closed")
    if db.get(Fighter, body.fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    if body.fighter_id not in access.gym_fighters(db, s.gym_id):
        raise HTTPException(
            status_code=422, detail="Only the gym's members: the fighter accepts the gym first"
        )
    if any(m.fighter_id == body.fighter_id for m in _members(db, s.id)):
        raise HTTPException(status_code=409, detail="Already on this squad")
    m = SquadMember(squad_id=s.id, fighter_id=body.fighter_id, added_by=viewer.user.id)
    db.add(m)
    db.flush()
    if body.is_main:
        _set_main(db, m)
    db.commit()
    return _out(db, s, viewer, detail=True)


def _member(db: DBSession, s: Squad, member_id: int) -> SquadMember:
    m = db.get(SquadMember, member_id)
    if m is None or m.squad_id != s.id or m.left_on is not None:
        raise HTTPException(status_code=404, detail="Not on this squad")
    return m


@router.patch("/squads/{squad_id}/members/{member_id}", response_model=SquadOut)
def set_main(
    squad_id: UUID,
    member_id: int,
    body: MainIn,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    """The fighter's main squad — the one their sessions are trained with unless
    they say otherwise. The fighter, or whoever runs the squad, sets it."""
    s = _squad(db, squad_id)
    m = _member(db, s, member_id)
    if viewer.own_fighter != m.fighter_id:
        _runs(viewer, s.gym_id)
    if body.is_main:
        _set_main(db, m)
    else:
        m.is_main = False
    db.add(m)
    db.commit()
    return _out(db, s, viewer, detail=viewer.own_fighter != m.fighter_id)


@router.post("/squads/{squad_id}/members/{member_id}/end", response_model=SquadOut)
def end_member(
    squad_id: UUID,
    member_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    """Off the squad — by whoever runs it, or the fighter leaving it."""
    s = _squad(db, squad_id)
    m = _member(db, s, member_id)
    if viewer.own_fighter != m.fighter_id:
        _runs(viewer, s.gym_id)
    m.left_on, m.is_main = dt.date.today(), False
    db.add(m)
    db.commit()
    return _out(db, s, viewer, detail=viewer.own_fighter != m.fighter_id)


@router.post(
    "/squads/{squad_id}/staff", response_model=SquadOut, status_code=status.HTTP_201_CREATED
)
def add_staff(
    squad_id: UUID,
    body: StaffIn,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    s = _squad(db, squad_id)
    _runs(viewer, s.gym_id)
    if not _open(s):
        raise HTTPException(status_code=409, detail="This squad is closed")
    if s.gym_id not in access.staff_gyms(db, body.coach_id):
        raise HTTPException(
            status_code=422,
            detail="Only the gym's coaching staff — invite them on the Staff page first",
        )
    if any(c.coach_id == body.coach_id for c in _staff(db, s.id)):
        raise HTTPException(status_code=409, detail="Already coaching this squad")
    db.add(
        SquadStaff(squad_id=s.id, coach_id=body.coach_id, role=body.role, added_by=viewer.user.id)
    )
    db.commit()
    return _out(db, s, viewer, detail=True)


@router.post("/squads/{squad_id}/staff/{staff_id}/end", response_model=SquadOut)
def end_staff(
    squad_id: UUID,
    staff_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> SquadOut:
    s = _squad(db, squad_id)
    _runs(viewer, s.gym_id)
    c = db.get(SquadStaff, staff_id)
    if c is None or c.squad_id != s.id or c.ended_on is not None:
        raise HTTPException(status_code=404, detail="Not coaching this squad")
    c.ended_on = dt.date.today()
    db.add(c)
    db.commit()
    return _out(db, s, viewer, detail=True)


@router.get("/fighters/{fighter_id}/squads", response_model=list[SquadOut])
def fighter_squads(
    fighter_id: UUID,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> list[SquadOut]:
    """The squads a fighter is on now, main first (the guard checks who may see the
    fighter)."""
    places = db.exec(
        select(SquadMember).where(
            SquadMember.fighter_id == fighter_id, col(SquadMember.left_on).is_(None)
        )
    ).all()
    out = []
    for m in places:
        s = db.get(Squad, m.squad_id)
        if s is not None and s.archived_at is None:
            row = _out(db, s, viewer)
            row.member_id, row.is_main = m.id, m.is_main
            out.append(row)
    return sorted(out, key=lambda s: (not s.is_main, s.name.lower()))


@router.get("/v2/my-squads", response_model=list[SquadOut])
def my_squads(
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> list[SquadOut]:
    """The squads the signed-in coach coaches, with their fighters."""
    if viewer.coach_id is None:
        return []
    ids = {
        c.squad_id
        for c in db.exec(
            select(SquadStaff).where(
                SquadStaff.coach_id == viewer.coach_id, col(SquadStaff.ended_on).is_(None)
            )
        ).all()
    }
    rows = [s for s in (db.get(Squad, i) for i in ids) if s is not None and _open(s)]
    return sorted((_out(db, s, viewer, detail=True) for s in rows), key=lambda s: s.name.lower())


def main_squad(db: DBSession, fighter_id: UUID) -> Squad | None:
    """A fighter's main squad, while it's open and they're on it."""
    m = db.exec(
        select(SquadMember).where(
            SquadMember.fighter_id == fighter_id,
            col(SquadMember.is_main),
            col(SquadMember.left_on).is_(None),
        )
    ).first()
    s = db.get(Squad, m.squad_id) if m else None
    return s if s is not None and _open(s) else None
