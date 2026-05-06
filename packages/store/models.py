"""SQLModel tables.

Pose keypoints are NOT in SQLite — they go to parquet on disk; the Session row
just holds a pointer (`pose_parquet_path`). HR samples and punch events are
tabular and live here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Stance(StrEnum):
    ORTHODOX = "orthodox"
    SOUTHPAW = "southpaw"
    SWITCH = "switch"


class SessionSourceEnum(StrEnum):
    LIVE_WEBCAM = "live_webcam"
    UPLOADED_VIDEO = "uploaded_video"
    LIVE_IPHONE = "live_iphone"
    POLAR_H10_ONLY = "polar_h10_only"
    HRV_REPLAY = "hrv_replay"


class SessionStatus(StrEnum):
    PENDING = "pending"
    CAPTURING = "capturing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class HandEnum(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class DetectionSourceEnum(StrEnum):
    HEURISTIC = "heuristic"
    LSTM_V1 = "lstm_v1"


class SkillLevel(StrEnum):
    """A spectrum from "I just punch a bag for fitness" to working trainer."""

    RECREATIONAL = "recreational"
    AMATEUR_NOVICE = "amateur_novice"
    AMATEUR_OPEN = "amateur_open"
    AMATEUR_ELITE = "amateur_elite"
    SEMI_PRO = "semi_pro"
    PROFESSIONAL = "professional"
    COACH = "coach"


# Common boxing weight classes. Stored as a string on the row so users can
# pick one but we don't have to model every sanctioning body's variations.
WEIGHT_CLASSES = (
    "minimumweight",  # ≤105 lb
    "light_flyweight",  # ≤108 lb
    "flyweight",  # ≤112 lb
    "super_flyweight",  # ≤115 lb
    "bantamweight",  # ≤118 lb
    "super_bantamweight",  # ≤122 lb
    "featherweight",  # ≤126 lb
    "super_featherweight",  # ≤130 lb
    "lightweight",  # ≤135 lb
    "super_lightweight",  # ≤140 lb
    "welterweight",  # ≤147 lb
    "super_welterweight",  # ≤154 lb
    "middleweight",  # ≤160 lb
    "super_middleweight",  # ≤168 lb
    "light_heavyweight",  # ≤175 lb
    "cruiserweight",  # ≤200 lb
    "heavyweight",  # ≤200+ lb
)


class Fighter(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Identity
    name: str = Field(index=True, min_length=1, max_length=120)
    nickname: str | None = Field(default=None, max_length=80)
    dob: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=16)  # "male" / "female" / other / None

    # Boxing stance + dominant side
    stance: Stance = Stance.ORTHODOX
    dominant_hand: HandEnum | None = None

    # Physical attributes — used for both display and CV calibration
    height_cm: float | None = Field(default=None, ge=80.0, le=250.0)
    reach_cm: float | None = Field(default=None, ge=80.0, le=260.0)
    weight_kg: float | None = Field(default=None, gt=0.0, le=400.0)
    shoulder_width_cm: float | None = Field(default=None, ge=20.0, le=80.0)

    # Competitive level
    skill_level: SkillLevel | None = None
    weight_class: str | None = Field(default=None, max_length=40)
    years_training: int | None = Field(default=None, ge=0, le=80)
    gym: str | None = Field(default=None, max_length=120)
    trainer: str | None = Field(default=None, max_length=120)

    # Record
    record_wins: int = Field(default=0, ge=0)
    record_losses: int = Field(default=0, ge=0)
    record_draws: int = Field(default=0, ge=0)
    record_kos: int = Field(default=0, ge=0)

    # External identifiers (registries / governing bodies)
    boxrec_id: str | None = Field(default=None, max_length=40)
    usa_boxing_id: str | None = Field(default=None, max_length=40)

    notes: str | None = None
    photo_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FighterCreate(SQLModel):
    """Light-weight create — most fields are filled in via Edit on the profile."""

    name: str = Field(min_length=1, max_length=120)
    dob: date | None = None
    stance: Stance = Stance.ORTHODOX


class FighterRead(SQLModel):
    id: UUID
    name: str
    nickname: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    stance: Stance
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
    record_wins: int = 0
    record_losses: int = 0
    record_draws: int = 0
    record_kos: int = 0
    boxrec_id: str | None = None
    usa_boxing_id: str | None = None
    notes: str | None = None
    photo_path: str | None = None
    created_at: datetime


class WeighIn(SQLModel, table=True):
    __tablename__ = "weigh_in"
    id: int | None = Field(default=None, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    weight_kg: float = Field(gt=0.0, le=400.0)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


class WeighInCreate(SQLModel):
    weight_kg: float = Field(gt=0.0, le=400.0)
    notes: str | None = None


class WeighInRead(SQLModel):
    id: int
    fighter_id: UUID
    weight_kg: float
    recorded_at: datetime
    notes: str | None = None


class Session(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    source: SessionSourceEnum
    status: SessionStatus = SessionStatus.PENDING
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    video_path: str | None = None
    pose_parquet_path: str | None = None
    frame_count: int = 0
    duration_ms: float = 0.0
    notes: str | None = None
    failure_reason: str | None = None
    # Pre-session resting HRV baseline (5-min recording before warmup).
    # Nullable: not all sessions have a baseline. When present, used as the
    # readiness predictor for that day's CV-derived performance score.
    baseline_rmssd_ms: float | None = None
    baseline_sdnn_ms: float | None = None
    baseline_mean_hr_bpm: float | None = None
    baseline_recorded_at: datetime | None = None


class SessionCreate(SQLModel):
    fighter_id: UUID
    source: SessionSourceEnum
    notes: str | None = None


class SessionRead(SQLModel):
    id: UUID
    fighter_id: UUID
    source: SessionSourceEnum
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    video_path: str | None
    pose_parquet_path: str | None
    failure_reason: str | None = None
    frame_count: int
    duration_ms: float
    notes: str | None
    baseline_rmssd_ms: float | None = None
    baseline_sdnn_ms: float | None = None
    baseline_mean_hr_bpm: float | None = None
    baseline_recorded_at: datetime | None = None


class LeadOrRearEnum(StrEnum):
    LEAD = "lead"
    REAR = "rear"


class VelocitySourceEnum(StrEnum):
    WORLD = "world"
    IMAGE_HEURISTIC = "image_heuristic"


class PunchTypeEnum(StrEnum):
    JAB = "jab"
    CROSS = "cross"
    HOOK = "hook"
    UPPERCUT = "uppercut"


class PunchEventRow(SQLModel, table=True):
    __tablename__ = "punch_event"
    id: int | None = Field(default=None, primary_key=True)
    session_id: UUID = Field(foreign_key="session.id", index=True)
    t_ms: float
    hand: HandEnum
    lead_or_rear: LeadOrRearEnum | None = None
    velocity_ms: float
    velocity_source: VelocitySourceEnum = VelocitySourceEnum.IMAGE_HEURISTIC
    punch_type: PunchTypeEnum | None = None
    detected_by: DetectionSourceEnum
    confidence: float


class PunchEventRead(SQLModel):
    session_id: UUID
    t_ms: float
    hand: HandEnum
    lead_or_rear: LeadOrRearEnum | None = None
    velocity_ms: float
    velocity_source: VelocitySourceEnum = VelocitySourceEnum.IMAGE_HEURISTIC
    punch_type: PunchTypeEnum | None = None
    detected_by: DetectionSourceEnum
    confidence: float


class HRSampleRow(SQLModel, table=True):
    __tablename__ = "hr_sample"
    id: int | None = Field(default=None, primary_key=True)
    session_id: UUID = Field(foreign_key="session.id", index=True)
    t_ms: float
    rr_ms: float
    hr_bpm: float


class HRSampleRead(SQLModel):
    session_id: UUID
    t_ms: float
    rr_ms: float
    hr_bpm: float


# ----------------------------------------------------------------------
# Coach + Referee profiles
# ----------------------------------------------------------------------


class CoachingLevel(StrEnum):
    AMATEUR = "amateur"
    PROFESSIONAL = "professional"
    BOTH = "both"


class Coach(SQLModel, table=True):
    """Coach profile — manages fighters, adds session observations."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Identity
    name: str = Field(min_length=1, max_length=120)
    photo_path: str | None = None
    dob: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=16)
    # Contact
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    # Coaching context
    gym: str | None = Field(default=None, max_length=120)
    specialties: str | None = Field(
        default=None,
        max_length=200,
        description="Free-form list, e.g. 'head movement, defense, conditioning'",
    )
    coaching_level: CoachingLevel | None = None
    years_experience: int | None = Field(default=None, ge=0, le=80)
    # Credentials
    certifications: str | None = Field(
        default=None,
        max_length=300,
        description="Comma-separated, e.g. 'USA Boxing Level 2, AIBA 1-Star'",
    )
    license_number: str | None = Field(default=None, max_length=80)
    license_expiry: date | None = None
    # Other
    languages: str | None = Field(
        default=None, max_length=200, description="Comma-separated"
    )
    notable_fighters: str | None = Field(
        default=None,
        max_length=400,
        description="Comma-separated names of notable fighters trained",
    )
    bio: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CoachCreate(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    gym: str | None = None
    specialties: str | None = None
    years_experience: int | None = None
    bio: str | None = None


class CoachRead(SQLModel):
    id: UUID
    name: str
    photo_path: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    email: str | None = None
    phone: str | None = None
    gym: str | None = None
    specialties: str | None = None
    coaching_level: CoachingLevel | None = None
    years_experience: int | None = None
    certifications: str | None = None
    license_number: str | None = None
    license_expiry: date | None = None
    languages: str | None = None
    notable_fighters: str | None = None
    bio: str | None = None
    notes: str | None = None
    created_at: datetime


class RefereeCertLevel(StrEnum):
    LOCAL = "local"
    REGIONAL = "regional"
    NATIONAL = "national"
    INTERNATIONAL = "international"


class Referee(SQLModel, table=True):
    """Referee profile — sanctioned official who oversees bouts."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Identity
    name: str = Field(min_length=1, max_length=120)
    photo_path: str | None = None
    dob: date | None = None
    nationality: str | None = Field(default=None, max_length=80)
    sex: str | None = Field(default=None, max_length=16)
    # Contact
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    # Credentials
    license_number: str | None = Field(default=None, max_length=80)
    sanctioning_body: str | None = Field(
        default=None,
        max_length=120,
        description="e.g. 'USA Boxing', 'WBA', 'BBBofC'",
    )
    certification_level: RefereeCertLevel | None = None
    license_expiry: date | None = None
    years_officiating: int | None = Field(default=None, ge=0, le=80)
    # Other
    languages: str | None = Field(default=None, max_length=200)
    notable_bouts: str | None = Field(
        default=None,
        max_length=400,
        description="Comma-separated, e.g. 'Mayweather vs Pacquiao 2015'",
    )
    bio: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RefereeCreate(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    license_number: str | None = None
    sanctioning_body: str | None = None
    license_expiry: date | None = None
    bio: str | None = None


class RefereeRead(SQLModel):
    id: UUID
    name: str
    photo_path: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    email: str | None = None
    phone: str | None = None
    license_number: str | None = None
    sanctioning_body: str | None = None
    certification_level: RefereeCertLevel | None = None
    license_expiry: date | None = None
    years_officiating: int | None = None
    languages: str | None = None
    notable_bouts: str | None = None
    bio: str | None = None
    notes: str | None = None
    created_at: datetime


# ----------------------------------------------------------------------
# Medical records (fighters only)
# ----------------------------------------------------------------------


class AllergySeverity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    ANAPHYLACTIC = "anaphylactic"


class ConditionStatus(StrEnum):
    ACTIVE = "active"
    MANAGED = "managed"
    RECOVERED = "recovered"


class MedicalRecord(SQLModel, table=True):
    """One-to-one medical record per fighter. Free-form fields are intentionally
    optional — the schema is wide so the dashboard can surface what's filled
    without forcing the coach to enter everything up front."""

    __tablename__ = "medical_record"
    fighter_id: UUID = Field(
        foreign_key="fighter.id", primary_key=True, index=True
    )
    blood_type: str | None = Field(default=None, max_length=4)  # "A+", "O-", etc.
    last_clearance_date: date | None = None
    clearing_physician: str | None = Field(default=None, max_length=120)
    primary_physician: str | None = Field(default=None, max_length=120)
    primary_physician_phone: str | None = Field(default=None, max_length=40)
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_relation: str | None = Field(default=None, max_length=80)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    insurance_provider: str | None = Field(default=None, max_length=120)
    insurance_policy: str | None = Field(default=None, max_length=80)
    notes: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MedicalRecordRead(SQLModel):
    fighter_id: UUID
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
    updated_at: datetime


class Allergy(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    substance: str = Field(min_length=1, max_length=120)
    severity: AllergySeverity = AllergySeverity.MILD
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AllergyCreate(SQLModel):
    substance: str = Field(min_length=1, max_length=120)
    severity: AllergySeverity = AllergySeverity.MILD
    notes: str | None = None


class AllergyRead(SQLModel):
    id: int
    fighter_id: UUID
    substance: str
    severity: AllergySeverity
    notes: str | None = None
    created_at: datetime


class Medication(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    name: str = Field(min_length=1, max_length=120)
    dose: str | None = Field(default=None, max_length=80)
    frequency: str | None = Field(default=None, max_length=80)  # "daily", "as needed"
    started_on: date | None = None
    prescribed_by: str | None = Field(default=None, max_length=120)
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MedicationCreate(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    dose: str | None = None
    frequency: str | None = None
    started_on: date | None = None
    prescribed_by: str | None = None
    is_active: bool = True
    notes: str | None = None


class MedicationRead(SQLModel):
    id: int
    fighter_id: UUID
    name: str
    dose: str | None = None
    frequency: str | None = None
    started_on: date | None = None
    prescribed_by: str | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime


class MedicalCondition(SQLModel, table=True):
    __tablename__ = "medical_condition"
    id: int | None = Field(default=None, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    name: str = Field(min_length=1, max_length=160)
    diagnosed_on: date | None = None
    status: ConditionStatus = ConditionStatus.ACTIVE
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MedicalConditionCreate(SQLModel):
    name: str = Field(min_length=1, max_length=160)
    diagnosed_on: date | None = None
    status: ConditionStatus = ConditionStatus.ACTIVE
    notes: str | None = None


class MedicalConditionRead(SQLModel):
    id: int
    fighter_id: UUID
    name: str
    diagnosed_on: date | None = None
    status: ConditionStatus
    notes: str | None = None
    created_at: datetime
