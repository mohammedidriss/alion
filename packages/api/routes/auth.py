"""Authentication routes — register, login, me."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator
from sqlmodel import Session as DBSession, select

from api.deps import db_session
from store import (
    CoachRepo,
    FighterRepo,
    RefereeRepo,
    User,
    UserCreate,
    UserRead,
    UserRepo,
    UserRole,
)
from store.models import FighterCreate, CoachCreate, RefereeCreate

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Security config ---
SECRET_KEY = os.environ.get("ALION_JWT_SECRET", "alion-dev-secret-key-change-in-production")  # noqa: S105
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days for dev convenience

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Helpers ---

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_access_token(user_id: UUID, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


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
    if user.role == UserRole.FIGHTER or user.role == "fighter":
        repo = FighterRepo(session)
        f = repo.create(FighterCreate(name=user.name, stance="orthodox"))
        return f.id  # type: ignore[return-value]
    if user.role == UserRole.COACH or user.role == "coach":
        repo = CoachRepo(session)
        c = repo.create(CoachCreate(name=user.name))
        return c.id  # type: ignore[return-value]
    if user.role == UserRole.REFEREE or user.role == "referee":
        repo = RefereeRepo(session)
        r = repo.create(RefereeCreate(name=user.name))
        return r.id  # type: ignore[return-value]
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


# --- Admin-only helpers ---

def _require_admin(user: User = Depends(require_current_user)) -> User:
    """Dependency that enforces admin role."""
    if user.role != UserRole.ADMIN and user.role != "admin":
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
    from store.models import Fighter, Coach, Gym, Session as TrainingSession
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
