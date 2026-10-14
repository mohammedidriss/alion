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
    basic profile (read)            F, F's coaches, F's gym managers, coaches at
                                    F's gym, researchers, admins
    basic profile (change)          F, F's coaches, F's gym managers, admins
    training data (read)            F, F's coaches, F's gym managers
      sessions, video, heart rate,
      wrist sensors, notes, weigh-ins
    training data (change)          F, F's coaches
    medical records                 F, F's coaches — every access logged
    research datasets               researchers only (ALION_RESEARCHERS)

"F's coaches" are coaches with a current assignment to F; "F's gym managers"
manage a gym F belongs to (and hasn't left). Admins manage accounts, gyms and
profiles — never training or medical data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from functools import cached_property
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.deps import db_session
from api.routes.auth import get_current_user
from api.services import researchers
from store import (
    AccessLog,
    Bout,
    Coach,
    CoachAssignment,
    DatasetTake,
    Fighter,
    GymManager,
    GymMembership,
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
        return self.user.role == UserRole.ADMIN

    @cached_property
    def researcher(self) -> bool:
        return researchers.is_researcher(self.user)

    @property
    def own_fighter(self) -> UUID | None:
        return self.user.profile_id if self.user.role == UserRole.FIGHTER else None

    @property
    def coach_id(self) -> UUID | None:
        return self.user.profile_id if self.user.role == UserRole.COACH else None

    @cached_property
    def manager_gym(self) -> UUID | None:
        if self.user.role != UserRole.GYM_MANAGER or self.user.profile_id is None:
            return None
        gm = self.db.get(GymManager, self.user.profile_id)
        return gm.gym_id if gm else None

    @cached_property
    def coached(self) -> set[UUID]:
        """Fighters with a current assignment to this coach."""
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
        }

    @cached_property
    def coach_gym_fighters(self) -> set[UUID]:
        """Fighters at this coach's gym — their basic profiles only."""
        if self.coach_id is None:
            return set()
        coach = self.db.get(Coach, self.coach_id)
        return gym_fighters(self.db, coach.gym_id) if coach and coach.gym_id else set()

    @cached_property
    def managed(self) -> set[UUID]:
        """Fighters at the gym this user manages."""
        return gym_fighters(self.db, self.manager_gym) if self.manager_gym else set()

    def can(self, fighter_id: UUID, level: Level) -> bool:
        is_self = fighter_id == self.own_fighter
        if level == Level.MEDICAL or level == Level.TRAINING_WRITE:
            return is_self or fighter_id in self.coached
        if level == Level.TRAINING:
            return is_self or fighter_id in self.coached or fighter_id in self.managed
        if level == Level.PROFILE_WRITE:
            return self.admin or is_self or fighter_id in self.coached or fighter_id in self.managed
        return (  # Level.PROFILE
            self.admin
            or self.researcher
            or is_self
            or fighter_id in self.coached
            or fighter_id in self.managed
            or fighter_id in self.coach_gym_fighters
        )

    def require(self, fighter_id: UUID, level: Level) -> None:
        if not self.can(fighter_id, level):
            raise forbidden(level)


def gym_fighters(db: DBSession, gym_id: UUID) -> set[UUID]:
    """Fighters at a gym: by their profile's gym, or a membership they accepted
    (ADR-035) and haven't left."""
    by_profile = set(db.exec(select(Fighter.id).where(Fighter.gym_id == gym_id)).all())
    rows = db.exec(
        select(GymMembership).where(
            GymMembership.gym_id == gym_id, GymMembership.member_type == "fighter"
        )
    ).all()
    joined = {
        m.member_id
        for m in rows
        if m.status not in ("left", "invited", "declined") and m.left_on is None
    }
    # Left, or invited back and not yet accepted: out, whatever their profile says.
    out = {
        m.member_id
        for m in rows
        if m.status in ("left", "invited", "declined") or m.left_on is not None
    } - joined
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
    """Research datasets: only the accounts in ALION_RESEARCHERS."""
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
    r"^/fighters/\{fighter_id\}(/(photo|titles|sponsors|coach-assignments)(/.*)?)?$"
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
    their fighters, their gym's managers and admins."""
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
    manages = viewer.manager_gym is not None and coach.gym_id == viewer.manager_gym
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
    if db.get(Bout, bout_id) is None:
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
    if viewer.admin or viewer.manager_gym == gym_id:
        return
    coach = db.get(Coach, viewer.coach_id) if viewer.coach_id else None
    if coach is not None and coach.gym_id == gym_id and not gym_page:
        return
    raise HTTPException(status_code=403, detail="Only this gym's managers, coaches or an admin")


# --------------------------------------------------------------------------
# Lists, creates, logging
# --------------------------------------------------------------------------


def visible_fighters(viewer: Viewer, level: Level) -> set[UUID] | None:
    """The fighters this viewer may see at `level` — None means all of them."""
    if level == Level.PROFILE and (viewer.admin or viewer.researcher):
        return None
    out: set[UUID] = set()
    if viewer.own_fighter:
        out.add(viewer.own_fighter)
    out |= viewer.coached
    if level in (Level.PROFILE, Level.PROFILE_WRITE, Level.TRAINING):
        out |= viewer.managed
    if level == Level.PROFILE:
        out |= viewer.coach_gym_fighters
    return out


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
