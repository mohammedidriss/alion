"""Who may see or change which fighter's data (ADR-017).

Every route is guarded by `guard`, an app-wide dependency: it reads the record
the route addresses from its path (a fighter, session, take, dataset, bout,
coach, gym, gym manager or referee) and applies the rule for it. A new route
that takes one of these ids is covered without anyone remembering to. Routes
that list or create records filter with `visible_fighters` / `require` instead.

The guard only adds record-level rules on top of authentication: with nobody
signed in it does nothing, and each route's own check (a login, a capture join
token) decides.

    data about fighter F            who
    ------------------------------  ---------------------------------------------
    basic profile (read)            F, F's coaches, F's physicians, F's gym
                                    managers, coaches at F's gym, admins
    basic profile (change)          F, F's coaches, F's gym managers, admins
    training data (read)            F, F's coaches, F's physicians, F's gym managers
      sessions, video, heart rate,
      wrist sensors, notes, weigh-ins
    training data (change)          F, F's coaches
    medical records (health notes)  F, F's physicians, F's coaches F allowed —
                                    every access logged
    research datasets               researchers
    everything above                researchers (ALION_RESEARCHERS, ADR-046) —
                                    and every administrator power

"F's coaches" are coaches with a current assignment to F; "F's physicians" are
physicians F chose (ADR-046); "F's gym managers" manage a gym F belongs to (and
hasn't left). Admins manage accounts, gyms and profiles — never training or
medical data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from functools import cached_property
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session as DBSession
from sqlmodel import col, or_, select

from api.deps import db_session
from api.routes.auth import get_current_user
from api.services import researchers
from store import (
    COACHING_ROLES,
    LEADING_ROLES,
    MANAGING_ROLES,
    AccessLog,
    Bout,
    Coach,
    CoachAssignment,
    DatasetTake,
    Fighter,
    GymManager,
    GymMembership,
    GymStaff,
    PhysicianAssignmentRow,
    Squad,
    SquadMember,
    SquadStaff,
    StaffStatus,
    User,
    UserRole,
)
from store import Session as SessionRow


class Level(StrEnum):
    PROFILE = "profile"
    PROFILE_WRITE = "profile_write"
    TRAINING = "training"
    TRAINING_WRITE = "training_write"
    MEDICAL = "medical"


@dataclass
class Viewer:
    """The signed-in user and the fighters they're linked to, worked out once per
    request (and only when a route needs it)."""

    user: User
    db: DBSession = field(repr=False)

    @property
    def role(self) -> str:
        return str(self.user.role)

    @property
    def admin(self) -> bool:
        """Accounts, gyms, profiles and settings: an admin, or a researcher (ADR-046)."""
        return self.user.role == UserRole.ADMIN or self.researcher

    @cached_property
    def researcher(self) -> bool:
        return researchers.is_researcher(self.user)

    @property
    def own_fighter(self) -> UUID | None:
        # A researcher's own training profile is a fighter's too (ADR-065).
        return (
            self.user.profile_id
            if self.user.role in (UserRole.FIGHTER, UserRole.RESEARCHER)
            else None
        )

    @property
    def coach_id(self) -> UUID | None:
        return self.user.profile_id if self.user.role == UserRole.COACH else None

    @cached_property
    def staff(self) -> list[GymStaff]:
        """This person's active roles at gyms (ADR-052), by account or coach profile."""
        who = [GymStaff.user_id == self.user.id]
        if self.coach_id is not None:
            who.append(GymStaff.coach_id == self.coach_id)
        q = select(GymStaff).where(or_(*who), GymStaff.status == StaffStatus.ACTIVE)
        return list(self.db.exec(q).all())

    def gyms_as(self, roles: frozenset[str]) -> set[UUID]:
        return {s.gym_id for s in self.staff if s.role in roles}

    @cached_property
    def managed_gyms(self) -> set[UUID]:
        """Gyms whose members, staff and settings this person manages: as owner or
        manager (ADR-052), or by a gym manager profile (ADR-017)."""
        out = self.gyms_as(MANAGING_ROLES)
        if self.user.role == UserRole.GYM_MANAGER and self.user.profile_id is not None:
            gm = self.db.get(GymManager, self.user.profile_id)
            if gm is not None:
                out.add(gm.gym_id)
        return out

    @cached_property
    def led_gyms(self) -> set[UUID]:
        """…and as head coach: the gym's fighters' training, and support-team links."""
        return self.managed_gyms | self.gyms_as(LEADING_ROLES)

    @cached_property
    def coach_gyms(self) -> set[UUID]:
        """Gyms this person coaches at (head coach or coach)."""
        return self.gyms_as(COACHING_ROLES)

    @cached_property
    def manager_gym(self) -> UUID | None:
        """The gym this person manages — their manager profile's, else one of their
        managed gyms (a fighter or coach a manager creates joins it)."""
        if self.user.role == UserRole.GYM_MANAGER and self.user.profile_id is not None:
            gm = self.db.get(GymManager, self.user.profile_id)
            if gm is not None:
                return gm.gym_id
        return min(self.managed_gyms, key=str) if self.managed_gyms else None

    @cached_property
    def coached(self) -> set[UUID]:
        """Fighters this coach coaches: a current assignment (their support team), or
        a squad they both are on (ADR-053)."""
        if self.coach_id is None:
            return set()
        today = date.today()
        rows = self.db.exec(
            select(CoachAssignment).where(CoachAssignment.coach_id == self.coach_id)
        ).all()
        return {
            a.fighter_id
            for a in rows
            if (a.ended_on is None or a.ended_on >= today)
            and (a.started_on is None or a.started_on <= today)
        } | squad_fighters(self.db, self.coach_id)

    @cached_property
    def coached_health(self) -> set[UUID]:
        """This coach's fighters who let them see their health notes (ADR-046)."""
        if self.coach_id is None:
            return set()
        today = date.today()
        rows = self.db.exec(
            select(CoachAssignment).where(
                CoachAssignment.coach_id == self.coach_id, col(CoachAssignment.health_access)
            )
        ).all()
        return {
            a.fighter_id
            for a in rows
            if (a.ended_on is None or a.ended_on >= today)
            and (a.started_on is None or a.started_on <= today)
        }

    @cached_property
    def physician_of(self) -> set[UUID]:
        """Fighters who chose this physician (ADR-046)."""
        if self.user.role != UserRole.PHYSICIAN:
            return set()
        rows = self.db.exec(
            select(PhysicianAssignmentRow).where(
                PhysicianAssignmentRow.physician_id == self.user.id,
                col(PhysicianAssignmentRow.ended_at).is_(None),
            )
        ).all()
        return {a.fighter_id for a in rows}

    @cached_property
    def coach_gym_fighters(self) -> set[UUID]:
        """Fighters at the gyms this person coaches at — their basic profiles only."""
        return set().union(*(gym_fighters(self.db, g) for g in self.coach_gyms))

    @cached_property
    def managed(self) -> set[UUID]:
        """Fighters at the gyms this person leads (owner, manager, head coach)."""
        return set().union(*(gym_fighters(self.db, g) for g in self.led_gyms))

    @cached_property
    def removed_fighters(self) -> set[UUID]:
        """Deleted profiles (ADR-056): kept, with their recordings, out of sight."""
        q = select(Fighter.id).where(col(Fighter.removed_at).is_not(None))
        return set(self.db.exec(q).all())

    def can(self, fighter_id: UUID, level: Level) -> bool:
        if self.researcher:
            return True  # everything, for the study (ADR-046); health-note reads are logged
        if fighter_id in self.removed_fighters:
            # A deleted profile: an admin may see and restore it; nobody else sees it.
            return self.admin and level in (Level.PROFILE, Level.PROFILE_WRITE)
        is_self = fighter_id == self.own_fighter
        if level == Level.MEDICAL:
            return is_self or fighter_id in self.coached_health or fighter_id in self.physician_of
        if level == Level.TRAINING_WRITE:
            return is_self or fighter_id in self.coached
        if level == Level.TRAINING:
            return (
                is_self
                or fighter_id in self.coached
                or fighter_id in self.managed
                or fighter_id in self.physician_of
            )
        if level == Level.PROFILE_WRITE:
            return self.admin or is_self or fighter_id in self.coached or fighter_id in self.managed
        return (  # Level.PROFILE
            self.admin
            or is_self
            or fighter_id in self.coached
            or fighter_id in self.managed
            or fighter_id in self.coach_gym_fighters
            or fighter_id in self.physician_of
        )

    def require(self, fighter_id: UUID, level: Level) -> None:
        if not self.can(fighter_id, level):
            raise forbidden(level)


def open_squads() -> Any:
    """A query for the squads that give access today: not archived, not past their
    end date."""
    today = date.today()
    return select(Squad.id).where(
        col(Squad.archived_at).is_(None),
        or_(col(Squad.ends_on).is_(None), col(Squad.ends_on) >= today),
    )


def squad_fighters(db: DBSession, coach_id: UUID) -> set[UUID]:
    """The fighters on the open squads this coach coaches, while both are on it."""
    mine = select(SquadStaff.squad_id).where(
        SquadStaff.coach_id == coach_id,
        col(SquadStaff.ended_on).is_(None),
        col(SquadStaff.squad_id).in_(open_squads()),
    )
    q = select(SquadMember.fighter_id).where(
        col(SquadMember.squad_id).in_(mine), col(SquadMember.left_on).is_(None)
    )
    return set(db.exec(q).all())


def staff_gyms(db: DBSession, coach_id: UUID) -> set[UUID]:
    """The gyms a coach profile is on the staff of, as head coach or coach."""
    q = select(GymStaff.gym_id).where(
        GymStaff.coach_id == coach_id,
        GymStaff.status == StaffStatus.ACTIVE,
        col(GymStaff.role).in_(COACHING_ROLES),
    )
    return set(db.exec(q).all())


def gym_coach_ids(db: DBSession, gym_id: UUID) -> list[UUID]:
    """The coach profiles on a gym's coaching staff (head coaches and coaches)."""
    q = select(GymStaff.coach_id).where(
        GymStaff.gym_id == gym_id,
        GymStaff.status == StaffStatus.ACTIVE,
        col(GymStaff.role).in_(COACHING_ROLES),
    )
    return [c for c in db.exec(q).all() if c is not None]


def gym_leaders(db: DBSession, gym_ids: set[UUID]) -> list[str]:
    """Who leads these gyms — sees their fighters' training: owners, managers and
    head coaches (ADR-052), and gym manager profiles (ADR-017)."""
    if not gym_ids:
        return []
    names = set(db.exec(select(GymManager.name).where(col(GymManager.gym_id).in_(gym_ids))).all())
    for s in db.exec(
        select(GymStaff).where(
            col(GymStaff.gym_id).in_(gym_ids),
            GymStaff.status == StaffStatus.ACTIVE,
            col(GymStaff.role).in_(LEADING_ROLES),
        )
    ).all():
        person = db.get(User, s.user_id) if s.user_id else None
        coach = db.get(Coach, s.coach_id) if s.coach_id else None
        name = person.name if person else coach.name if coach else None
        if name:
            names.add(name)
    return sorted(names)


def gym_fighters(db: DBSession, gym_id: UUID) -> set[UUID]:
    """Fighters at a gym: by their profile's gym, or a membership they accepted
    (ADR-035) and haven't left."""
    by_profile = set(db.exec(select(Fighter.id).where(Fighter.gym_id == gym_id)).all())
    rows = db.exec(
        select(GymMembership).where(
            GymMembership.gym_id == gym_id, GymMembership.member_type == "fighter"
        )
    ).all()
    waiting = ("left", "invited", "declined", "applied")  # applied: until the gym approves
    joined = {m.member_id for m in rows if m.status not in waiting and m.left_on is None}
    # Left, or invited back (or asked) and not yet in: out, whatever their profile says.
    out = {m.member_id for m in rows if m.status in waiting or m.left_on is not None} - joined
    return (by_profile - out) | joined


_WHAT: dict[str, str] = {
    Level.MEDICAL: "this fighter's medical records",
    Level.TRAINING: "this fighter's training data",
    Level.TRAINING_WRITE: "this fighter's training data",
    Level.PROFILE: "this fighter",
    Level.PROFILE_WRITE: "this fighter's profile",
}


def forbidden(level: Level | str) -> HTTPException:
    what = _WHAT.get(str(level), str(level))
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"No access to {what}")


def current_viewer(
    user: User | None = Depends(get_current_user), db: DBSession = Depends(db_session)
) -> Viewer | None:
    return Viewer(user, db) if user else None


def require_viewer(viewer: Viewer | None = Depends(current_viewer)) -> Viewer:
    if viewer is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return viewer


def require_researcher(viewer: Viewer = Depends(require_viewer)) -> Viewer:
    """Research datasets, model training, studies: only the accounts in ALION_RESEARCHERS."""
    if not viewer.researcher:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Research datasets are open to researchers only",
        )
    return viewer


def require_admin_viewer(viewer: Viewer = Depends(require_viewer)) -> Viewer:
    if not viewer.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an admin")
    return viewer


# --------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------

_MEDICAL = re.compile(
    r"^/fighters/\{fighter_id\}/(medical|allergies|medications|conditions|pupil-readings)\b"
)
_PROFILE = re.compile(
    # …and deleting or restoring the profile (ADR-056): the route decides who may.
    r"^/fighters/\{fighter_id\}"
    r"(/(photo|titles|sponsors|coach-assignments|removal|remove-account|restore)(/.*)?)?$"
)
_RESEARCH = re.compile(r"^/(v2/)?(takes|datasets)(/|$)|^/studies/rq1/ratings$")


def _uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    return re.sub(r"^/v1(?=/)", "", path)


async def guard(
    request: Request,
    viewer: Viewer | None = Depends(current_viewer),
    db: DBSession = Depends(db_session),
) -> None:
    """Apply the record-level rule for whatever record this route addresses."""
    if viewer is None:
        return  # not signed in: the route's own authentication decides
    path = _route_path(request)
    params = request.path_params
    write = request.method not in ("GET", "HEAD", "OPTIONS")

    if _RESEARCH.match(path):
        require_researcher(viewer)
        return

    fighter_id = _uuid(params.get("fighter_id"))
    session_id = _uuid(params.get("session_id"))
    coach_id = _uuid(params.get("coach_id"))

    if coach_id is not None:
        _coach_rule(viewer, coach_id, fighter_id, path, write)
        return
    if session_id is not None:
        row = db.get(SessionRow, session_id)
        if row is not None:
            if row.removed_at is not None and not viewer.researcher:
                # A deleted session (ADR-056): kept for the study, gone for everyone else.
                raise HTTPException(status_code=404, detail="session not found")
            viewer.require(row.fighter_id, Level.TRAINING_WRITE if write else Level.TRAINING)
        return
    if fighter_id is not None:
        if db.get(Fighter, fighter_id) is None:
            return  # the route answers 404
        if _MEDICAL.match(path):
            allowed = viewer.can(fighter_id, Level.MEDICAL)
            log_access(db, viewer, fighter_id, path, "write" if write else "read", allowed)
            if not allowed:
                raise forbidden(Level.MEDICAL)
        elif _PROFILE.match(path):
            viewer.require(fighter_id, Level.PROFILE_WRITE if write else Level.PROFILE)
        else:
            viewer.require(fighter_id, Level.TRAINING_WRITE if write else Level.TRAINING)
        return
    bout_id = _uuid(params.get("bout_id"))
    if bout_id is not None:
        _bout_rule(viewer, db, bout_id, write)
        return
    gym_id = _uuid(params.get("gym_id"))
    if gym_id is not None:
        _gym_rule(viewer, db, gym_id, path, write)
        return
    manager_id = _uuid(params.get("manager_id"))
    if (
        manager_id is not None
        and write
        and not (viewer.admin or viewer.user.profile_id == manager_id)
    ):
        raise HTTPException(status_code=403, detail="Only an admin or this gym manager")
    referee_id = _uuid(params.get("referee_id"))
    if (
        referee_id is not None
        and write
        and not (viewer.admin or viewer.user.profile_id == referee_id)
    ):
        raise HTTPException(status_code=403, detail="Only an admin or this referee")


def _coach_rule(
    viewer: Viewer, coach_id: UUID, fighter_id: UUID | None, path: str, write: bool
) -> None:
    """A coach's own pages: notes are theirs alone; the profile is seen by them,
    their fighters, their gym's managers and admins. Researchers see all (ADR-046)."""
    if viewer.researcher:
        return
    me = viewer.coach_id == coach_id
    if "/notes" in path:
        if not me:
            raise HTTPException(status_code=403, detail="Only this coach")
        if fighter_id is not None:
            viewer.require(fighter_id, Level.TRAINING_WRITE)
        return
    coach = viewer.db.get(Coach, coach_id)
    if coach is None:
        return
    manages = bool(viewer.managed_gyms & (staff_gyms(viewer.db, coach_id) | {coach.gym_id}))
    if write:
        if not (me or viewer.admin or manages):
            raise HTTPException(status_code=403, detail="Only an admin, this coach or their gym")
        return
    coaches_me = viewer.own_fighter is not None and viewer.own_fighter in _fighters_of(
        viewer.db, coach_id
    )
    if not (me or viewer.admin or manages or coaches_me):
        raise HTTPException(status_code=403, detail="No access to this coach")


def _fighters_of(db: DBSession, coach_id: UUID) -> set[UUID]:
    today = date.today()
    rows = db.exec(select(CoachAssignment).where(CoachAssignment.coach_id == coach_id)).all()
    return {a.fighter_id for a in rows if a.ended_on is None or a.ended_on >= today}


def _bout_rule(viewer: Viewer, db: DBSession, bout_id: UUID, write: bool) -> None:
    """A bout is open to whoever may see (or change) either corner's session; an
    empty bout to the coaches and gym managers who set fights up."""
    if db.get(Bout, bout_id) is None or viewer.researcher:
        return
    fighters = list(db.exec(select(SessionRow.fighter_id).where(SessionRow.bout_id == bout_id)))
    level = Level.TRAINING_WRITE if write else Level.TRAINING
    if fighters:
        if not any(viewer.can(f, level) for f in fighters):
            raise forbidden(level)
    elif viewer.role not in (UserRole.COACH, UserRole.GYM_MANAGER) and viewer.own_fighter is None:
        raise HTTPException(status_code=403, detail="No access to this bout")


def _gym_rule(viewer: Viewer, db: DBSession, gym_id: UUID, path: str, write: bool) -> None:
    """A gym's own details are open to anyone signed in. Its members and check-ins
    are open to its managers, its coaches and admins. Changing or deleting the
    gym itself is for its managers and admins."""
    gym_page = path.rstrip("/").endswith("{gym_id}")
    if gym_page and not write:
        return
    if viewer.admin or gym_id in viewer.managed_gyms:
        return
    if gym_id in viewer.led_gyms | viewer.coach_gyms and not gym_page:
        return
    raise HTTPException(status_code=403, detail="Only this gym's managers, coaches or an admin")


# --------------------------------------------------------------------------
# Lists, creates, logging
# --------------------------------------------------------------------------


def visible_fighters(viewer: Viewer, level: Level) -> set[UUID] | None:
    """The fighters this viewer may see at `level` — None means all of them."""
    if viewer.researcher or (level == Level.PROFILE and viewer.admin):
        return None
    out: set[UUID] = set()
    if viewer.own_fighter:
        out.add(viewer.own_fighter)
    out |= viewer.coached
    if level in (Level.PROFILE, Level.PROFILE_WRITE, Level.TRAINING):
        out |= viewer.managed
    if level in (Level.PROFILE, Level.TRAINING):
        out |= viewer.physician_of
    if level == Level.PROFILE:
        out |= viewer.coach_gym_fighters
    return out - viewer.removed_fighters


def take_fighter(db: DBSession, take_id: UUID) -> UUID | None:
    take = db.get(DatasetTake, take_id)
    return take.fighter_id if take else None


def log_access(
    db: DBSession, viewer: Viewer, fighter_id: UUID, resource: str, action: str, allowed: bool
) -> None:
    db.add(
        AccessLog(
            user_id=viewer.user.id,
            role=viewer.role,
            fighter_id=fighter_id,
            resource=resource,
            action=action,
            allowed=allowed,
        )
    )
    db.commit()


def access_log(db: DBSession, fighter_id: UUID, limit: int = 200) -> list[AccessLog]:
    return list(
        db.exec(
            select(AccessLog)
            .where(AccessLog.fighter_id == fighter_id)
            .order_by(col(AccessLog.at).desc())
            .limit(limit)
        ).all()
    )
