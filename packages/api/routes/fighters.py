"""Fighter CRUD + weigh-in tracking + longitudinal observations."""

from __future__ import annotations

import json as _json
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from analyze import compute_readiness, compute_score, compute_swc
from analyze.readiness import MIN_HISTORY
from api.deps import (
    coach_note_repo,
    db_session,
    fighter_repo,
    fighter_team_repo,
    medical_repo,
    punch_event_repo,
    resolve_gym_id,
    session_repo,
)
from api.routes.auth import get_current_user, require_current_user
from api.services.photos import delete_photos_for, save_photo
from store import (
    WEIGHT_CLASSES,
    AllergyCreate,
    AllergyRead,
    CoachAssignmentCreate,
    CoachAssignmentRead,
    CoachNoteRead,
    CoachNoteRepo,
    CoachRole,
    FighterRepo,
    FighterSponsorCreate,
    FighterSponsorRead,
    FighterTeamRepo,
    FighterTitleCreate,
    FighterTitleRead,
    HandEnum,
    MedicalConditionCreate,
    MedicalConditionRead,
    MedicalRecordRead,
    MedicalRepo,
    MedicationCreate,
    MedicationRead,
    PunchEventRepo,
    SessionRepo,
    SkillLevel,
    Stance,
    TitleStatus,
    User,
    WeighInCreate,
    WeighInRead,
    WeighInRepo,
)
from store.models import FighterCreate, FighterRead

router = APIRouter(
    prefix="/fighters",
    tags=["fighters"],
    dependencies=[Depends(require_current_user)],
)


class FighterUpdate(BaseModel):
    """Patch payload — every field optional. Send only the keys you want to change."""

    name: str | None = None
    nickname: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    stance: Stance | None = None
    dominant_hand: HandEnum | None = None
    height_cm: float | None = None
    reach_cm: float | None = None
    weight_kg: float | None = None
    shoulder_width_cm: float | None = None
    skill_level: SkillLevel | None = None
    weight_class: str | None = None
    years_training: int | None = None
    gym: str | None = None
    trainer: str | None = None
    record_wins: int | None = None
    record_losses: int | None = None
    record_draws: int | None = None
    record_kos: int | None = None
    boxrec_id: str | None = None
    usa_boxing_id: str | None = None
    notes: str | None = None
    bio: str | None = None
    career_history: str | None = None


@router.get("/options", tags=["fighters"])
def fighter_options() -> dict[str, list[str]]:
    """Static enums + dropdown options the dashboard needs to populate forms."""
    return {
        "stances": [s.value for s in Stance],
        "hands": [h.value for h in HandEnum],
        "skill_levels": [s.value for s in SkillLevel],
        "weight_classes": list(WEIGHT_CLASSES),
        "sexes": ["male", "female", "other"],
    }


@router.post("", response_model=FighterRead, status_code=status.HTTP_201_CREATED)
def create_fighter(data: FighterCreate, repo: FighterRepo = Depends(fighter_repo)) -> FighterRead:
    fighter = repo.create(data)
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.get("", response_model=list[FighterRead])
def list_fighters(
    gym_id: UUID | None = None,
    repo: FighterRepo = Depends(fighter_repo),
    current_user: User | None = Depends(get_current_user),
    session: DBSession = Depends(db_session),
) -> list[FighterRead]:
    # Gym managers can only see their own gym's fighters
    if current_user and current_user.role == "gym_manager":
        scoped_gym = resolve_gym_id(current_user, session)
        if scoped_gym:
            gym_id = scoped_gym  # override any client-supplied gym_id
    rows = repo.list_for_gym(gym_id) if gym_id else repo.list_all()
    return [FighterRead.model_validate(f, from_attributes=True) for f in rows]


@router.get("/{fighter_id}", response_model=FighterRead)
def get_fighter(fighter_id: UUID, repo: FighterRepo = Depends(fighter_repo)) -> FighterRead:
    fighter = repo.get(fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.patch("/{fighter_id}", response_model=FighterRead)
def update_fighter(
    fighter_id: UUID,
    data: FighterUpdate,
    repo: FighterRepo = Depends(fighter_repo),
) -> FighterRead:
    # exclude_unset: only the fields the client actually sent are included.
    patch = data.model_dump(exclude_unset=True)
    fighter = repo.update(fighter_id, patch)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.delete("/{fighter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fighter(fighter_id: UUID, repo: FighterRepo = Depends(fighter_repo)) -> None:
    if not repo.delete(fighter_id):
        raise HTTPException(status_code=404, detail="fighter not found")
    delete_photos_for("fighter", fighter_id)


# ---- weigh-ins ----


@router.get("/{fighter_id}/weigh-ins", response_model=list[WeighInRead])
def list_weigh_ins(
    fighter_id: UUID,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> list[WeighInRead]:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = WeighInRepo(db).list_for_fighter(fighter_id)
    return [WeighInRead.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/{fighter_id}/weigh-ins", response_model=WeighInRead, status_code=status.HTTP_201_CREATED
)
def create_weigh_in(
    fighter_id: UUID,
    data: WeighInCreate,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> WeighInRead:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = WeighInRepo(db).create(fighter_id, data)
    return WeighInRead.model_validate(row, from_attributes=True)


@router.delete("/{fighter_id}/weigh-ins/{weigh_in_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weigh_in(
    fighter_id: UUID,
    weigh_in_id: int,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> None:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    if not WeighInRepo(db).delete(weigh_in_id):
        raise HTTPException(status_code=404, detail="weigh-in not found")


# ---- weight analysis ----


class WeightAnalysis(BaseModel):
    """AI-powered weight management analysis."""

    total_entries: int
    current_kg: float | None = None
    min_kg: float | None = None
    max_kg: float | None = None
    range_kg: float | None = None
    mean_kg: float | None = None
    std_kg: float | None = None
    cv_pct: float | None = None  # coefficient of variation %
    trend_direction: str | None = None  # "gaining", "losing", "stable"
    trend_kg_per_week: float | None = None
    instability_flag: bool = False
    ai_summary: str = ""
    ai_recommendations: list[str] = []


@router.get("/{fighter_id}/weight-analysis", response_model=WeightAnalysis)
async def weight_analysis(
    fighter_id: UUID,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> WeightAnalysis:
    """Analyse weight history for instability patterns and provide AI advice."""
    fighter = repo.get(fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = WeighInRepo(db).list_for_fighter(fighter_id)
    if len(rows) < 2:
        return WeightAnalysis(
            total_entries=len(rows),
            current_kg=rows[0].weight_kg if rows else None,
            ai_summary="Not enough weigh-in data to analyse. Log at least 2 weigh-ins.",
        )

    # Sort by date
    entries = sorted(rows, key=lambda w: w.recorded_at)
    weights = [w.weight_kg for w in entries]
    n = len(weights)

    # Basic stats
    mean_w = sum(weights) / n
    var_w = sum((w - mean_w) ** 2 for w in weights) / n
    std_w = var_w**0.5
    cv_pct = (std_w / mean_w * 100) if mean_w else 0.0

    # Trend via simple linear regression (days since first entry)
    t0 = entries[0].recorded_at
    days = [(w.recorded_at - t0).total_seconds() / 86400 for w in entries]
    mean_d = sum(days) / n
    cov_dw = sum((d - mean_d) * (w - mean_w) for d, w in zip(days, weights, strict=False)) / n
    var_d = sum((d - mean_d) ** 2 for d in days) / n
    slope_per_day = cov_dw / var_d if var_d > 0 else 0.0
    trend_per_week = slope_per_day * 7

    if abs(trend_per_week) < 0.15:
        direction = "stable"
    elif trend_per_week > 0:
        direction = "gaining"
    else:
        direction = "losing"

    # Instability detection: flag if CV > 2% or large swings between consecutive entries
    consecutive_swings = [abs(weights[i + 1] - weights[i]) for i in range(n - 1)]
    max_swing = max(consecutive_swings)
    avg_swing = sum(consecutive_swings) / len(consecutive_swings)
    big_swings = sum(1 for s in consecutive_swings if s > mean_w * 0.02)  # >2% of mean
    instability = cv_pct > 2.0 or big_swings >= 2 or max_swing > mean_w * 0.04

    # Build data payload for AI
    data_for_ai = {
        "fighter_name": fighter.name,
        "weight_class": fighter.weight_class,
        "target_weight_kg": fighter.weight_kg,
        "entries": [
            {"date": w.recorded_at.isoformat()[:10], "kg": w.weight_kg, "notes": w.notes}
            for w in entries
        ],
        "stats": {
            "mean_kg": round(mean_w, 2),
            "std_kg": round(std_w, 2),
            "cv_pct": round(cv_pct, 2),
            "min_kg": round(min(weights), 2),
            "max_kg": round(max(weights), 2),
            "range_kg": round(max(weights) - min(weights), 2),
            "trend_direction": direction,
            "trend_kg_per_week": round(trend_per_week, 3),
            "max_consecutive_swing_kg": round(max_swing, 2),
            "avg_consecutive_swing_kg": round(avg_swing, 2),
            "big_swings_count": big_swings,
            "instability_detected": instability,
        },
    }

    # Generate AI advice
    from coach import generate_corner_advice

    system_prompt = (
        "You are an elite boxing nutritionist and weight management specialist. "
        "Analyse the fighter's weigh-in history and statistics below. "
        "Focus on:\n"
        "1. Weight stability — are there concerning fluctuations?\n"
        "2. Trend analysis — is the fighter trending toward or away from their weight class?\n"
        "3. Rate of change — is weight gain/loss too rapid (unhealthy) or on track?\n"
        "4. Practical advice — nutrition timing, hydration, safe cutting strategies.\n"
        "5. Red flags — yo-yo patterns, crash dieting signs, dehydration risk.\n\n"
        'Return JSON: {"summary": "2-3 sentence overview", '
        '"action_items": ["advice 1", "advice 2", ...]}\n'
        "Be specific to the data. Reference actual numbers."
    )
    import json as json_mod

    advice = await generate_corner_advice(system_prompt, json_mod.dumps(data_for_ai))

    return WeightAnalysis(
        total_entries=n,
        current_kg=weights[-1],
        min_kg=round(min(weights), 2),
        max_kg=round(max(weights), 2),
        range_kg=round(max(weights) - min(weights), 2),
        mean_kg=round(mean_w, 2),
        std_kg=round(std_w, 2),
        cv_pct=round(cv_pct, 2),
        trend_direction=direction,
        trend_kg_per_week=round(trend_per_week, 3),
        instability_flag=instability,
        ai_summary=advice.summary,
        ai_recommendations=advice.action_items,
    )


class MatrixPoint(BaseModel):
    session_id: UUID
    started_at: datetime
    baseline_rmssd_ms: float
    baseline_sdnn_ms: float | None = None
    baseline_mean_hr_bpm: float | None = None
    peak_velocity_p90: float
    ppm: float
    duration_min: float
    score: float
    punch_count: int


class MatrixResponse(BaseModel):
    fighter_id: UUID
    points: list[MatrixPoint]
    pearson_r: float | None = None
    slope: float | None = None
    intercept: float | None = None
    # Hopkins' Smallest Worthwhile Change for the score series.
    # None when fewer than 3 sessions in the matrix.
    swc: float | None = None


def _pearson(xs: list[float], ys: list[float]) -> tuple[float | None, float | None, float | None]:
    n = len(xs)
    if n < 3:
        return None, None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    if sxx == 0 or syy == 0:
        return None, None, None
    r = sxy / (sxx**0.5 * syy**0.5)
    slope = sxy / sxx
    intercept = my - slope * mx
    return round(r, 4), round(slope, 4), round(intercept, 4)


class ReadinessResponse(BaseModel):
    fighter_id: UUID
    score: int
    mode: str  # "z_score" | "absolute"
    rmssd_ms: float | None = None
    history_n: int
    baseline_mean_ms: float | None = None
    baseline_sd_ms: float | None = None
    z: float | None = None
    min_history_required: int = MIN_HISTORY


@router.get("/{fighter_id}/readiness", response_model=ReadinessResponse | None)
def fighter_readiness(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    sessions: SessionRepo = Depends(session_repo),
) -> ReadinessResponse | None:
    """Per-fighter readiness using z-score against the fighter's own RMSSD
    history. Falls back to legacy absolute remap when history is insufficient
    (< MIN_HISTORY baselines). Returns None if no baseline has been recorded
    at all."""
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = sessions.list_for_fighter(fighter_id)
    baselined = sorted(
        (s for s in rows if s.baseline_rmssd_ms is not None),
        key=lambda s: s.baseline_recorded_at or s.started_at,
    )
    if not baselined:
        return None
    latest = baselined[-1]
    history = [s.baseline_rmssd_ms for s in baselined[:-1] if s.baseline_rmssd_ms is not None]
    assert latest.baseline_rmssd_ms is not None
    r = compute_readiness(latest.baseline_rmssd_ms, history)
    return ReadinessResponse(
        fighter_id=fighter_id,
        score=r.score,
        mode=r.mode,
        rmssd_ms=r.rmssd_ms,
        history_n=r.history_n,
        baseline_mean_ms=r.baseline_mean_ms,
        baseline_sd_ms=r.baseline_sd_ms,
        z=r.z,
    )


@router.get("/{fighter_id}/matrix", response_model=MatrixResponse)
def fighter_matrix(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> MatrixResponse:
    """Per-session points joining resting HRV baseline with CV performance.

    Returns only sessions that have BOTH a baseline RMSSD and at least one
    detected punch — i.e. enough data to be a usable scatter point.
    """
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = sessions.list_for_fighter(fighter_id)
    points: list[MatrixPoint] = []
    for s in rows:
        if s.baseline_rmssd_ms is None:
            continue
        ev = events.list_for_session(s.id)
        if not ev:
            continue
        score = compute_score([e.velocity_ms for e in ev], s.duration_ms)
        points.append(
            MatrixPoint(
                session_id=s.id,
                started_at=s.started_at,
                baseline_rmssd_ms=s.baseline_rmssd_ms,
                baseline_sdnn_ms=s.baseline_sdnn_ms,
                baseline_mean_hr_bpm=s.baseline_mean_hr_bpm,
                peak_velocity_p90=score.peak_velocity_p90,
                ppm=score.ppm,
                duration_min=score.duration_min,
                score=score.score,
                punch_count=len(ev),
            )
        )
    xs = [p.baseline_rmssd_ms for p in points]
    ys = [p.score for p in points]
    r, slope, intercept = _pearson(xs, ys)
    return MatrixResponse(
        fighter_id=fighter_id,
        points=points,
        pearson_r=r,
        slope=slope,
        intercept=intercept,
        swc=compute_swc(ys),
    )


# ----------------------------------------------------------------------
# Photo upload
# ----------------------------------------------------------------------


@router.post("/{fighter_id}/photo", response_model=FighterRead)
async def upload_fighter_photo(
    fighter_id: UUID,
    file: UploadFile = File(...),
    repo: FighterRepo = Depends(fighter_repo),
) -> FighterRead:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    path = await save_photo("fighter", fighter_id, file)
    row = repo.update(fighter_id, {"photo_path": path})
    assert row is not None
    return FighterRead.model_validate(row, from_attributes=True)


# ----------------------------------------------------------------------
# Medical record (one-to-one with fighter)
# ----------------------------------------------------------------------


class MedicalRecordPatch(BaseModel):
    blood_type: str | None = None
    last_clearance_date: date | None = None
    clearing_physician: str | None = None
    primary_physician: str | None = None
    primary_physician_phone: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relation: str | None = None
    emergency_contact_phone: str | None = None
    insurance_provider: str | None = None
    insurance_policy: str | None = None
    notes: str | None = None


@router.get("/{fighter_id}/medical", response_model=MedicalRecordRead | None)
def get_medical_record(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> MedicalRecordRead | None:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = med.get_record(fighter_id)
    if row is None:
        return None
    return MedicalRecordRead.model_validate(row, from_attributes=True)


@router.patch("/{fighter_id}/medical", response_model=MedicalRecordRead)
def upsert_medical_record(
    fighter_id: UUID,
    data: MedicalRecordPatch,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> MedicalRecordRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = med.upsert_record(fighter_id, data.model_dump(exclude_unset=True))
    return MedicalRecordRead.model_validate(row, from_attributes=True)


# --- Allergies ---


@router.get("/{fighter_id}/allergies", response_model=list[AllergyRead])
def list_allergies(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> list[AllergyRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return [
        AllergyRead.model_validate(a, from_attributes=True) for a in med.list_allergies(fighter_id)
    ]


@router.post(
    "/{fighter_id}/allergies",
    response_model=AllergyRead,
    status_code=status.HTTP_201_CREATED,
)
def add_allergy(
    fighter_id: UUID,
    data: AllergyCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> AllergyRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = med.add_allergy(fighter_id, data)
    return AllergyRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{fighter_id}/allergies/{allergy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_allergy(
    fighter_id: UUID,
    allergy_id: int,
    med: MedicalRepo = Depends(medical_repo),
) -> None:
    if not med.delete_allergy(fighter_id, allergy_id):
        raise HTTPException(status_code=404, detail="allergy not found")


# --- Medications ---


@router.get("/{fighter_id}/medications", response_model=list[MedicationRead])
def list_medications(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> list[MedicationRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return [
        MedicationRead.model_validate(m, from_attributes=True)
        for m in med.list_medications(fighter_id)
    ]


@router.post(
    "/{fighter_id}/medications",
    response_model=MedicationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_medication(
    fighter_id: UUID,
    data: MedicationCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> MedicationRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = med.add_medication(fighter_id, data)
    return MedicationRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{fighter_id}/medications/{medication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_medication(
    fighter_id: UUID,
    medication_id: int,
    med: MedicalRepo = Depends(medical_repo),
) -> None:
    if not med.delete_medication(fighter_id, medication_id):
        raise HTTPException(status_code=404, detail="medication not found")


# --- Medical conditions ---


@router.get("/{fighter_id}/conditions", response_model=list[MedicalConditionRead])
def list_conditions(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> list[MedicalConditionRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return [
        MedicalConditionRead.model_validate(c, from_attributes=True)
        for c in med.list_conditions(fighter_id)
    ]


@router.post(
    "/{fighter_id}/conditions",
    response_model=MedicalConditionRead,
    status_code=status.HTTP_201_CREATED,
)
def add_condition(
    fighter_id: UUID,
    data: MedicalConditionCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    med: MedicalRepo = Depends(medical_repo),
) -> MedicalConditionRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = med.add_condition(fighter_id, data)
    return MedicalConditionRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{fighter_id}/conditions/{condition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_condition(
    fighter_id: UUID,
    condition_id: int,
    med: MedicalRepo = Depends(medical_repo),
) -> None:
    if not med.delete_condition(fighter_id, condition_id):
        raise HTTPException(status_code=404, detail="condition not found")


# ----------------------------------------------------------------------
# Team — titles, sponsors, coach assignments
# ----------------------------------------------------------------------

# --- Titles ---


@router.get("/{fighter_id}/titles", response_model=list[FighterTitleRead])
def list_titles(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> list[FighterTitleRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return [
        FighterTitleRead.model_validate(t, from_attributes=True)
        for t in team.list_titles(fighter_id)
    ]


@router.post(
    "/{fighter_id}/titles",
    response_model=FighterTitleRead,
    status_code=status.HTTP_201_CREATED,
)
def add_title(
    fighter_id: UUID,
    data: FighterTitleCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> FighterTitleRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = team.add_title(fighter_id, data)
    return FighterTitleRead.model_validate(row, from_attributes=True)


@router.delete("/{fighter_id}/titles/{title_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_title(
    fighter_id: UUID,
    title_id: int,
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> None:
    if not team.delete_title(fighter_id, title_id):
        raise HTTPException(status_code=404, detail="title not found")


# --- Sponsors ---


@router.get("/{fighter_id}/sponsors", response_model=list[FighterSponsorRead])
def list_sponsors(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> list[FighterSponsorRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return [
        FighterSponsorRead.model_validate(s, from_attributes=True)
        for s in team.list_sponsors(fighter_id)
    ]


@router.post(
    "/{fighter_id}/sponsors",
    response_model=FighterSponsorRead,
    status_code=status.HTTP_201_CREATED,
)
def add_sponsor(
    fighter_id: UUID,
    data: FighterSponsorCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> FighterSponsorRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = team.add_sponsor(fighter_id, data)
    return FighterSponsorRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{fighter_id}/sponsors/{sponsor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_sponsor(
    fighter_id: UUID,
    sponsor_id: int,
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> None:
    if not team.delete_sponsor(fighter_id, sponsor_id):
        raise HTTPException(status_code=404, detail="sponsor not found")


# --- Coach assignments ---


@router.get(
    "/{fighter_id}/coach-assignments",
    response_model=list[CoachAssignmentRead],
)
def list_coach_assignments(
    fighter_id: UUID,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> list[CoachAssignmentRead]:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    out: list[CoachAssignmentRead] = []
    for a, coach_name, coach_photo_path in team.list_coach_assignments(fighter_id):
        out.append(
            CoachAssignmentRead(
                id=a.id,
                fighter_id=a.fighter_id,
                coach_id=a.coach_id,
                coach_name=coach_name,
                coach_photo_path=coach_photo_path,
                role=a.role,
                started_on=a.started_on,
                ended_on=a.ended_on,
                notes=a.notes,
                created_at=a.created_at,
            )
        )
    return out


@router.post(
    "/{fighter_id}/coach-assignments",
    response_model=CoachAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_coach_assignment(
    fighter_id: UUID,
    data: CoachAssignmentCreate,
    fighters: FighterRepo = Depends(fighter_repo),
    team: FighterTeamRepo = Depends(fighter_team_repo),
    db: DBSession = Depends(db_session),
) -> CoachAssignmentRead:
    if fighters.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    from store import CoachRepo

    coach = CoachRepo(db).get(data.coach_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="coach not found")
    row = team.add_coach_assignment(fighter_id, data)
    return CoachAssignmentRead(
        id=row.id,
        fighter_id=row.fighter_id,
        coach_id=row.coach_id,
        coach_name=coach.name,
        coach_photo_path=coach.photo_path,
        role=row.role,
        started_on=row.started_on,
        ended_on=row.ended_on,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.delete(
    "/{fighter_id}/coach-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_coach_assignment(
    fighter_id: UUID,
    assignment_id: int,
    team: FighterTeamRepo = Depends(fighter_team_repo),
) -> None:
    if not team.delete_coach_assignment(fighter_id, assignment_id):
        raise HTTPException(status_code=404, detail="assignment not found")


# --- Coach roles enum (for the UI dropdown) ---


@router.get("/_meta/coach-roles", response_model=list[str])
def list_coach_roles() -> list[str]:
    return [r.value for r in CoachRole]


@router.get("/_meta/title-statuses", response_model=list[str])
def list_title_statuses() -> list[str]:
    return [t.value for t in TitleStatus]


# ---------------------------------------------------------------------------
# Longitudinal AI observations
# ---------------------------------------------------------------------------


class FighterObservationResponse(BaseModel):
    observations: list[str]
    strengths: list[str]
    weaknesses: list[str]
    training_plan: list[str]
    summary: str


class PerformanceTrendItem(BaseModel):
    date: str
    punch_count: int
    peak_velocity_ms: float
    ppm: float
    score: float
    duration_min: float
    baseline_rmssd_ms: float | None = None


class PerformanceTrendResponse(BaseModel):
    months: int
    sessions_count: int
    items: list[PerformanceTrendItem]


@router.get(
    "/{fighter_id}/performance-trend",
    response_model=PerformanceTrendResponse,
)
def get_performance_trend(
    fighter_id: UUID,
    months: int = 3,
    repo: FighterRepo = Depends(fighter_repo),
    session_repo_dep: SessionRepo = Depends(session_repo),
    event_repo: PunchEventRepo = Depends(punch_event_repo),
) -> PerformanceTrendResponse:
    """Return per-session performance metrics for the last N months."""
    fighter = repo.get(fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")

    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    all_sessions = session_repo_dep.list_for_fighter(fighter_id)
    completed = [
        s for s in all_sessions if s.status.value == "completed" and s.started_at >= cutoff
    ]
    completed.sort(key=lambda s: s.started_at)

    items: list[PerformanceTrendItem] = []
    for s in completed:
        events = event_repo.list_for_session(s.id)
        velocities = [e.velocity_ms for e in events]
        duration_min = (s.duration_ms / 1000.0) / 60.0 if s.duration_ms > 0 else 0.0
        ppm = len(events) / max(duration_min, 1e-6) if events else 0.0
        p90 = _percentile_90(sorted(velocities)) if velocities else 0.0
        score = p90 * (ppm / 60.0) * duration_min
        items.append(
            PerformanceTrendItem(
                date=s.started_at.strftime("%Y-%m-%d"),
                punch_count=len(events),
                peak_velocity_ms=round(p90, 2),
                ppm=round(ppm, 1),
                score=round(score, 2),
                duration_min=round(duration_min, 2),
                baseline_rmssd_ms=s.baseline_rmssd_ms,
            )
        )

    return PerformanceTrendResponse(
        months=months,
        sessions_count=len(items),
        items=items,
    )


@router.post(
    "/{fighter_id}/observations/generate",
    response_model=FighterObservationResponse,
)
async def generate_fighter_observations(
    fighter_id: UUID,
    repo: FighterRepo = Depends(fighter_repo),
    session_repo_dep: SessionRepo = Depends(session_repo),
    event_repo: PunchEventRepo = Depends(punch_event_repo),
) -> FighterObservationResponse:
    """Generate LLM-based longitudinal observations from the last 3 months."""
    fighter = repo.get(fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")

    # Gather completed sessions from the last 3 months.
    cutoff = datetime.utcnow() - timedelta(days=90)
    all_sessions = session_repo_dep.list_for_fighter(fighter_id)
    completed = [
        s for s in all_sessions if s.status.value == "completed" and s.started_at >= cutoff
    ]
    completed.sort(key=lambda s: s.started_at)

    if len(completed) < 2:
        return FighterObservationResponse(
            observations=["Not enough completed sessions in the last 3 months for analysis."],
            strengths=[],
            weaknesses=[],
            training_plan=["Complete more training sessions to enable trend analysis."],
            summary="Insufficient data — need at least 2 completed sessions in the last 3 months.",
        )

    # Build per-session summaries.
    session_summaries = []
    for s in completed:
        events = event_repo.list_for_session(s.id)
        velocities = [e.velocity_ms for e in events]
        duration_min = (s.duration_ms / 1000.0) / 60.0 if s.duration_ms > 0 else 0.0
        ppm = len(events) / max(duration_min, 1e-6) if events else 0.0
        p90 = _percentile_90(sorted(velocities)) if velocities else 0.0
        score = p90 * (ppm / 60.0) * duration_min

        session_summaries.append(
            {
                "date": s.started_at.strftime("%Y-%m-%d"),
                "punch_count": len(events),
                "peak_velocity_ms": round(p90, 2),
                "ppm": round(ppm, 1),
                "score": round(score, 2),
                "duration_min": round(duration_min, 2),
                "baseline_rmssd_ms": s.baseline_rmssd_ms,
                "coach_notes": s.notes or None,
            }
        )

    # Compute trend deltas (first half vs second half).
    mid = len(session_summaries) // 2
    first_half = session_summaries[:mid] if mid > 0 else session_summaries[:1]
    second_half = session_summaries[mid:] if mid > 0 else session_summaries[1:]

    def _avg(items: list[dict[str, Any]], key: str) -> float:
        vals = [i[key] for i in items if i[key] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    trend = {
        "velocity_change_pct": round(
            (
                (_avg(second_half, "peak_velocity_ms") - _avg(first_half, "peak_velocity_ms"))
                / max(_avg(first_half, "peak_velocity_ms"), 1e-6)
            )
            * 100,
            1,
        ),
        "ppm_change_pct": round(
            (
                (_avg(second_half, "ppm") - _avg(first_half, "ppm"))
                / max(_avg(first_half, "ppm"), 1e-6)
            )
            * 100,
            1,
        ),
        "score_change_pct": round(
            (
                (_avg(second_half, "score") - _avg(first_half, "score"))
                / max(_avg(first_half, "score"), 1e-6)
            )
            * 100,
            1,
        ),
        "sessions_count": len(completed),
        "period_days": (completed[-1].started_at - completed[0].started_at).days,
    }

    # Build fighter profile.
    age = None
    if fighter.dob:
        age = (datetime.utcnow().date() - fighter.dob).days // 365

    fighter_info = {
        "name": fighter.name,
        "stance": fighter.stance.value if fighter.stance else None,
        "weight_class": fighter.weight_class,
        "age": age,
    }

    # Send only the last 15 sessions to stay within LLM context limits,
    # but trends are computed from the full 3-month window above.
    recent_summaries = session_summaries[-15:]
    # Strip None coach_notes to save tokens.
    for ss in recent_summaries:
        if ss["coach_notes"] is None:
            del ss["coach_notes"]
        if ss["baseline_rmssd_ms"] is None:
            del ss["baseline_rmssd_ms"]

    payload = _json.dumps(
        {
            "fighter": fighter_info,
            "sessions": recent_summaries,
            "trend_summary": trend,
        }
    )

    from coach import FIGHTER_OBSERVATION_SYSTEM_PROMPT
    from coach.llm_client import generate_raw

    raw_text = await generate_raw(FIGHTER_OBSERVATION_SYSTEM_PROMPT, payload)

    # Parse the structured observation JSON from the LLM response.
    data = _parse_observation_json(raw_text)
    if data:
        return FighterObservationResponse(
            observations=data.get("observations", []),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            training_plan=data.get("training_plan", []),
            summary=data.get("summary", ""),
        )

    # Fallback: return the raw text as a single observation.
    return FighterObservationResponse(
        observations=[raw_text[:500]] if raw_text else ["No response from LLM."],
        strengths=[],
        weaknesses=[],
        training_plan=[],
        summary=raw_text[:300] if raw_text else "Unable to generate structured observations.",
    )


# ------------------------------------------------------------------
# Coach notes on a fighter (read-only from fighter side)
# ------------------------------------------------------------------


@router.get("/{fighter_id}/coach-notes", response_model=list[CoachNoteRead])
def list_fighter_coach_notes(
    fighter_id: UUID,
    repo: CoachNoteRepo = Depends(coach_note_repo),
    frepo: FighterRepo = Depends(fighter_repo),
) -> list[CoachNoteRead]:
    """All notes from all coaches on this fighter, newest first."""
    if frepo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = repo.list_for_fighter(fighter_id)
    return [
        CoachNoteRead(
            id=note.id,
            coach_id=note.coach_id,
            fighter_id=note.fighter_id,
            coach_name=cname,
            coach_photo_path=cphoto,
            content=note.content,
            created_at=note.created_at,
        )
        for note, cname, cphoto in rows
    ]


def _parse_observation_json(text: str) -> dict[str, Any] | None:
    """Extract the first balanced JSON object containing 'observations'."""
    import re

    s = text.strip()
    # Strip markdown fences.
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # Find first balanced {...}.
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = _json.loads(s[start : i + 1])
                    if isinstance(data, dict):
                        return data
                except _json.JSONDecodeError:
                    pass
                break
    return None


def _percentile_90(sorted_vals: list[float]) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * 0.9
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - (k - lo)) + sorted_vals[hi] * (k - lo)
