"""Authentication routes — register, login, me."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator
from sqlmodel import Session as DBSession
from sqlmodel import select

from api.deps import db_session
from store import (
    CoachRepo,
    FighterRepo,
    GymManagerRepo,
    RefereeRepo,
    User,
    UserCreate,
    UserRead,
    UserRepo,
    UserRole,
)
from store.models import CoachCreate, FighterCreate, RefereeCreate

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Security config ---
_DEV_SECRET = "alion-dev-secret-key-change-in-production"
SECRET_KEY = os.environ.get("ALION_JWT_SECRET", _DEV_SECRET)
if SECRET_KEY == _DEV_SECRET:
    import warnings
    warnings.warn(
        "ALION_JWT_SECRET is not set — using insecure default. "
        "Set this env var before deploying to production.",
        stacklevel=1,
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days for dev convenience

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Helpers ---


def _hash_password(password: str) -> str:
    return str(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())


def _verify_password(plain: str, hashed: str) -> bool:
    return bool(bcrypt.checkpw(plain.encode(), hashed.encode()))


def _create_access_token(user_id: UUID, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return str(jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM))


def _user_repo(session: DBSession = Depends(db_session)) -> UserRepo:
    return UserRepo(session)


# --- Dependency: get current user from token ---


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: DBSession = Depends(db_session),
) -> User | None:
    """Returns the current user or None if not authenticated."""
    if token is None:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    repo = UserRepo(session)
    user = repo.get(UUID(user_id))
    if user is None or not user.is_active:
        return None
    return user


async def require_current_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Like get_current_user but raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# --- Request / Response schemas ---


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: UserRole = UserRole.FIGHTER

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Name is required")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


# --- Routes ---


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    repo: UserRepo = Depends(_user_repo),
    session: DBSession = Depends(db_session),
) -> TokenResponse:
    """Create a new user account, auto-create a linked profile, and return a JWT."""
    existing = repo.get_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user_create = UserCreate(
        email=data.email,
        password=data.password,
        name=data.name,
        role=data.role,
    )
    hashed = _hash_password(data.password)
    user = repo.create(user_create, hashed)

    # Auto-create a linked profile based on role
    profile_id = _create_profile_for_role(user, session)
    if profile_id:
        repo.set_profile_id(user.id, profile_id)
        user.profile_id = profile_id

    token = _create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user, from_attributes=True),
    )


def _create_profile_for_role(user: User, session: DBSession) -> UUID | None:
    """Create a profile entity matching the user's role and return its id."""
    if user.role == UserRole.FIGHTER:
        f_repo = FighterRepo(session)
        f = f_repo.create(FighterCreate(name=user.name, stance="orthodox"))
        return f.id
    if user.role == UserRole.COACH:
        c_repo = CoachRepo(session)
        c = c_repo.create(CoachCreate(name=user.name))
        return c.id
    if user.role == UserRole.REFEREE:
        r_repo = RefereeRepo(session)
        r = r_repo.create(RefereeCreate(name=user.name))
        return r.id
    # gym_manager profiles need a gym — created later when assigned to a gym
    return None


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: UserRepo = Depends(_user_repo),
) -> TokenResponse:
    """Authenticate with email + password, return a JWT."""
    user = repo.get_by_email(form_data.username.lower().strip())
    if user is None or not _verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    token = _create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user, from_attributes=True),
    )


@router.get("/me", response_model=UserRead)
def get_me(user: User = Depends(require_current_user)) -> UserRead:
    """Return the current authenticated user."""
    return UserRead.model_validate(user, from_attributes=True)


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    current_password: str | None = None
    new_password: str | None = None


@router.patch("/me", response_model=UserRead)
def update_me(
    data: UpdateProfileRequest,
    user: User = Depends(require_current_user),
    repo: UserRepo = Depends(_user_repo),
    session: DBSession = Depends(db_session),
) -> UserRead:
    """Update the current user's profile (name, email, password)."""
    fields: dict[str, Any] = {}

    if data.name is not None:
        name = data.name.strip()
        if len(name) < 1:
            raise HTTPException(status_code=422, detail="Name cannot be empty")
        fields["name"] = name
        # Also sync name on linked profile
        if user.profile_id:
            _sync_profile_name(user, name, session)

    if data.email is not None:
        email = data.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(status_code=422, detail="Invalid email format")
        if email != user.email:
            existing = repo.get_by_email(email)
            if existing:
                raise HTTPException(status_code=409, detail="Email already in use")
            fields["email"] = email

    if data.new_password is not None:
        if not data.current_password:
            raise HTTPException(
                status_code=422, detail="Current password is required to set a new one"
            )
        if not _verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        if len(data.new_password) < 6:
            raise HTTPException(
                status_code=422, detail="New password must be at least 6 characters"
            )
        fields["password_hash"] = _hash_password(data.new_password)

    if not fields:
        return UserRead.model_validate(user, from_attributes=True)

    updated = repo.update(user.id, fields)
    return UserRead.model_validate(updated, from_attributes=True)


def _sync_profile_name(user: User, new_name: str, session: DBSession) -> None:
    """Keep the linked profile's name in sync with the user account name."""
    role = str(user.role).lower()
    if role == "fighter":
        f_repo = FighterRepo(session)
        f = f_repo.get(user.profile_id)  # type: ignore[arg-type]
        if f:
            f.name = new_name
            session.add(f)
            session.commit()
    elif role == "coach":
        c_repo = CoachRepo(session)
        c = c_repo.get(user.profile_id)  # type: ignore[arg-type]
        if c:
            c.name = new_name
            session.add(c)
            session.commit()
    elif role == "gym_manager":
        gm_repo = GymManagerRepo(session)
        gm = gm_repo.get(user.profile_id)  # type: ignore[arg-type]
        if gm:
            gm.name = new_name
            session.add(gm)
            session.commit()


# --- Admin-only helpers ---


def _require_admin(user: User = Depends(require_current_user)) -> User:
    """Dependency that enforces admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# --- Admin endpoints ---


@router.get("/admin/users", response_model=list[UserRead])
def admin_list_users(
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> list[UserRead]:
    """List all users in the system (admin only)."""
    return [UserRead.model_validate(u, from_attributes=True) for u in repo.list_all()]


class AdminCreateUserRequest(BaseModel):
    email: str
    password: str
    name: str
    role: UserRole

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


@router.post("/admin/users", response_model=UserRead, status_code=201)
def admin_create_user(
    data: AdminCreateUserRequest,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
    session: DBSession = Depends(db_session),
) -> UserRead:
    """Create a user account (admin only). Auto-creates profile for non-gym_manager roles."""
    existing = repo.get_by_email(data.email.lower().strip())
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_create = UserCreate(email=data.email.lower().strip(), password=data.password, name=data.name.strip(), role=data.role)
    hashed = _hash_password(data.password)
    user = repo.create(user_create, hashed)
    profile_id = _create_profile_for_role(user, session)
    if profile_id:
        repo.set_profile_id(user.id, profile_id)
        user.profile_id = profile_id
    return UserRead.model_validate(user, from_attributes=True)


class AdminResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


@router.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: UUID,
    data: AdminResetPasswordRequest,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> dict[str, str]:
    """Reset any user's password (admin only)."""
    target = repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    new_hash = _hash_password(data.new_password)
    repo.update(user_id, {"password_hash": new_hash})
    return {"status": "ok", "message": f"Password reset for {target.email}"}


class AdminUpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    profile_id: UUID | None = None


@router.patch("/admin/users/{user_id}", response_model=UserRead)
def admin_update_user(
    user_id: UUID,
    data: AdminUpdateUserRequest,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> UserRead:
    """Update any user's fields (admin only)."""
    target = repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = repo.update(user_id, fields)
    return UserRead.model_validate(updated, from_attributes=True)


@router.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: UUID,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> dict[str, str]:
    """Delete a user account (admin only). Cannot delete yourself."""
    if user_id == _admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    target = repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    repo.delete(user_id)
    return {"status": "ok", "message": f"Deleted user {target.email}"}


@router.post("/admin/users/{user_id}/deactivate")
def admin_deactivate_user(
    user_id: UUID,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> dict[str, str]:
    """Deactivate a user (soft disable, preserves data)."""
    if user_id == _admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    target = repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    repo.update(user_id, {"is_active": False})
    return {"status": "ok", "message": f"Deactivated {target.email}"}


@router.post("/admin/users/{user_id}/activate")
def admin_activate_user(
    user_id: UUID,
    _admin: User = Depends(_require_admin),
    repo: UserRepo = Depends(_user_repo),
) -> dict[str, str]:
    """Re-activate a previously deactivated user."""
    target = repo.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    repo.update(user_id, {"is_active": True})
    return {"status": "ok", "message": f"Activated {target.email}"}


class AdminSystemStats(BaseModel):
    total_users: int
    active_users: int
    fighters: int
    coaches: int
    gym_managers: int
    admins: int
    gyms: int
    sessions: int


@router.get("/admin/stats", response_model=AdminSystemStats)
def admin_system_stats(
    _admin: User = Depends(_require_admin),
    session: DBSession = Depends(db_session),
) -> AdminSystemStats:
    """System-wide statistics (admin only)."""
    from store.models import Gym
    from store.models import Session as TrainingSession

    users = list(session.exec(select(User)).all())
    return AdminSystemStats(
        total_users=len(users),
        active_users=sum(1 for u in users if u.is_active),
        fighters=sum(1 for u in users if u.role in (UserRole.FIGHTER, "fighter")),
        coaches=sum(1 for u in users if u.role in (UserRole.COACH, "coach")),
        gym_managers=sum(1 for u in users if u.role in (UserRole.GYM_MANAGER, "gym_manager")),
        admins=sum(1 for u in users if u.role in (UserRole.ADMIN, "admin")),
        gyms=len(list(session.exec(select(Gym)).all())),
        sessions=len(list(session.exec(select(TrainingSession)).all())),
    )
