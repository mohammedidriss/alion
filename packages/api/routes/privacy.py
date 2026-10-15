"""Privacy and consent, for the person signed in (ADR-033).

GET  /v2/privacy/me                 what Alion keeps about me, who can see it, my
                                    consent (terms, research datasets), my requests
POST /v2/privacy/requests           ask for a copy of my data, its deletion, or to
                                    leave the research datasets (one open per kind)
GET  /v2/privacy/requests           every request — admins and researchers
PATCH /v2/privacy/requests/{id}     close one, with a note — admins and researchers

Requests are acted on by a person, not done automatically: deleting or
withdrawing touches coaches' records and research data, and an export is checked
before it leaves this computer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, gym_fighters, gym_leaders, require_viewer
from api.deps import db_session
from api.services import disk_encryption, terms
from store import (
    Allergy,
    Coach,
    CoachAssignment,
    CoachNote,
    Dataset,
    DatasetParticipant,
    Fighter,
    Gym,
    GymMembership,
    HRSampleRow,
    IMUSampleRow,
    MedicalCondition,
    Medication,
    PhysicianAssignmentRow,
    User,
)
from store import Session as SessionRow
from store.models import (
    AdviceRecord,
    DataRequestKind,
    DataRequestRow,
    DataRequestStatus,
    UtcDatetime,
)

router = APIRouter(prefix="/v2/privacy", tags=["privacy"])


def require_handler(viewer: Viewer = Depends(require_viewer)) -> Viewer:
    """Admins (accounts) and researchers (research datasets) act on requests."""
    if not (viewer.admin or viewer.researcher):
        raise HTTPException(
            status_code=403, detail="Only an admin or a researcher handles requests"
        )
    return viewer


class Holding(BaseModel):
    what: str
    count: int


class Viewers(BaseModel):
    coaches: list[str]  # current coaches: training data
    coaches_with_health: list[str] = []  # …and the health notes, shared by the fighter (ADR-046)
    physicians: list[str] = []  # chosen by the fighter: health notes and training data
    gyms: list[str]  # gyms they're a member of: training data, not health notes
    gym_managers: list[str]


class DatasetConsent(BaseModel):
    dataset: str
    code: str | None
    consent: str
    consent_date: date | None


class RequestOut(BaseModel):
    id: UUID
    kind: str
    note: str | None
    status: str
    created_at: UtcDatetime
    handled_at: UtcDatetime | None
    response: str | None


class PrivacyOut(BaseModel):
    role: str
    terms_version: str | None
    terms_accepted_at: UtcDatetime | None
    terms_current: str
    holdings: list[Holding]
    viewers: Viewers | None  # for a fighter: who can see their data right now
    datasets: list[DatasetConsent]
    requests: list[RequestOut]
    disk_encrypted: str = "unknown"  # on / off / unknown: this computer's disk (ADR-044)


def _count(db: DBSession, stmt: object) -> int:
    return int(db.exec(stmt).one())  # type: ignore[call-overload]


def _request_out(r: DataRequestRow) -> RequestOut:
    return RequestOut(
        id=r.id,
        kind=str(r.kind),
        note=r.note,
        status=str(r.status),
        created_at=r.created_at,
        handled_at=r.handled_at,
        response=r.response,
    )


@router.get("/me", response_model=PrivacyOut)
def my_privacy(
    viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> PrivacyOut:
    user = viewer.user
    holdings = [Holding(what="Your account (name, email, role, photo)", count=1)]
    viewers: Viewers | None = None
    datasets: list[DatasetConsent] = []
    fid = viewer.own_fighter
    if fid is not None:
        sessions = [
            s.id for s in db.exec(select(SessionRow).where(SessionRow.fighter_id == fid)).all()
        ]
        ids = sessions or [UUID(int=0)]
        me = db.get(Fighter, fid)
        if me is not None and me.emergency_contact_name:
            # Seen by those who see your profile: coaches, your gym's staff, physicians.
            holdings.append(Holding(what="Your emergency contact (name, phone)", count=1))
        holdings += [
            Holding(what="Training sessions (video clips, pose, punches)", count=len(sessions)),
            Holding(
                what="Sessions with heart rate from the chest strap",
                count=_count(
                    db,
                    select(func.count(func.distinct(HRSampleRow.session_id))).where(
                        col(HRSampleRow.session_id).in_(ids)
                    ),
                ),
            ),
            Holding(
                what="Sessions with wrist-sensor data",
                count=_count(
                    db,
                    select(func.count(func.distinct(IMUSampleRow.session_id))).where(
                        col(IMUSampleRow.session_id).in_(ids)
                    ),
                ),
            ),
            Holding(
                what="Health notes (allergies, medications, conditions)",
                count=sum(
                    _count(db, select(func.count()).select_from(t).where(t.fighter_id == fid))
                    for t in (Allergy, Medication, MedicalCondition)
                ),
            ),
            Holding(
                what="Coach notes about you",
                count=_count(
                    db,
                    select(func.count()).select_from(CoachNote).where(CoachNote.fighter_id == fid),
                ),
            ),
            Holding(
                what="AI training advice written for you",
                count=_count(
                    db,
                    select(func.count())
                    .select_from(AdviceRecord)
                    .where(AdviceRecord.fighter_id == fid),
                ),
            ),
        ]
        today = date.today()
        coach_ids = {
            a.coach_id
            for a in db.exec(select(CoachAssignment).where(CoachAssignment.fighter_id == fid)).all()
            if (a.ended_on is None or a.ended_on >= today)
            and (a.started_on is None or a.started_on <= today)
        }
        coaches = [
            c.name
            for c in db.exec(
                select(Coach).where(col(Coach.id).in_(coach_ids or {UUID(int=0)}))
            ).all()
        ]
        fighter = db.get(Fighter, fid)
        gym_ids = {
            m.gym_id
            for m in db.exec(select(GymMembership).where(GymMembership.member_id == fid)).all()
        }
        if fighter and fighter.gym_id:
            gym_ids.add(fighter.gym_id)
        gym_ids = {g for g in gym_ids if fid in gym_fighters(db, g)}  # the ones they haven't left
        gyms = db.exec(select(Gym).where(col(Gym.id).in_(gym_ids or {UUID(int=0)}))).all()
        managers = gym_leaders(db, gym_ids)  # owners, managers, head coaches (ADR-052)
        shared = {
            a.coach_id
            for a in db.exec(
                select(CoachAssignment).where(
                    CoachAssignment.fighter_id == fid, col(CoachAssignment.health_access)
                )
            ).all()
            if (a.ended_on is None or a.ended_on >= today)
        } & coach_ids
        with_health = [
            c.name
            for c in db.exec(select(Coach).where(col(Coach.id).in_(shared or {UUID(int=0)}))).all()
        ]
        physicians = [
            u.name
            for a in db.exec(
                select(PhysicianAssignmentRow).where(
                    PhysicianAssignmentRow.fighter_id == fid,
                    col(PhysicianAssignmentRow.ended_at).is_(None),
                )
            ).all()
            if (u := db.get(User, a.physician_id)) is not None
        ]
        viewers = Viewers(
            coaches=sorted(coaches),
            coaches_with_health=sorted(with_health),
            physicians=sorted(physicians),
            gyms=sorted(g.name for g in gyms),
            gym_managers=managers,
        )
        for p in db.exec(
            select(DatasetParticipant).where(DatasetParticipant.fighter_id == fid)
        ).all():
            ds = db.get(Dataset, p.dataset_id)
            datasets.append(
                DatasetConsent(
                    dataset=ds.name if ds else "—",
                    code=p.code,
                    consent=str(p.consent),
                    consent_date=p.consent_date,
                )
            )
    elif user.profile_id is not None and str(user.role) == "coach":
        holdings.append(
            Holding(
                what="Notes you wrote about fighters",
                count=_count(
                    db,
                    select(func.count())
                    .select_from(CoachNote)
                    .where(CoachNote.coach_id == user.profile_id),
                ),
            )
        )
    mine = db.exec(
        select(DataRequestRow)
        .where(DataRequestRow.user_id == user.id)
        .order_by(col(DataRequestRow.created_at).desc())
    ).all()
    return PrivacyOut(
        role=str(user.role),
        terms_version=user.terms_version,
        terms_accepted_at=user.terms_accepted_at,
        terms_current=terms.TERMS_VERSION,
        holdings=holdings,
        viewers=viewers,
        datasets=datasets,
        requests=[_request_out(r) for r in mine],
        disk_encrypted=disk_encryption.status(),
    )


class RequestIn(BaseModel):
    kind: DataRequestKind
    note: str | None = Field(default=None, max_length=2000)


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def make_request(
    body: RequestIn, viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> RequestOut:
    open_one = db.exec(
        select(DataRequestRow).where(
            DataRequestRow.user_id == viewer.user.id,
            DataRequestRow.kind == body.kind,
            DataRequestRow.status == DataRequestStatus.OPEN,
        )
    ).first()
    if open_one is not None:
        raise HTTPException(status_code=409, detail="You already have one of these open")
    row = DataRequestRow(
        user_id=viewer.user.id, kind=body.kind, note=(body.note or "").strip() or None
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _request_out(row)


class HandledRequest(RequestOut):
    user_name: str
    user_email: str
    user_role: str


@router.get("/requests", response_model=list[HandledRequest])
def all_requests(
    _: Viewer = Depends(require_handler), db: DBSession = Depends(db_session)
) -> list[HandledRequest]:
    rows = db.exec(select(DataRequestRow).order_by(col(DataRequestRow.created_at).desc())).all()
    out = []
    for r in rows:
        u = db.get(User, r.user_id)
        out.append(
            HandledRequest(
                **_request_out(r).model_dump(),
                user_name=u.name if u else "—",
                user_email=u.email if u else "—",
                user_role=str(u.role) if u else "—",
            )
        )
    return out


class CloseIn(BaseModel):
    status: Literal["done", "declined"]
    response: str = Field(min_length=1, max_length=2000)


@router.patch("/requests/{request_id}", response_model=RequestOut)
def close_request(
    request_id: UUID,
    body: CloseIn,
    viewer: Viewer = Depends(require_handler),
    db: DBSession = Depends(db_session),
) -> RequestOut:
    row = db.get(DataRequestRow, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="request not found")
    if row.status != DataRequestStatus.OPEN:
        raise HTTPException(status_code=409, detail="Already closed")
    row.status = DataRequestStatus(body.status)
    row.response = body.response.strip()
    row.handled_by = viewer.user.id
    row.handled_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _request_out(row)
