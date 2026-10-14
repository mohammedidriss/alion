"""The appropriate-reliance study (ADR-026) — adapted from the Proposal V2 test build.

Researchers (ALION_RESEARCHERS) enrol reviewers once their signed consent is
checked, add adjudicated advisory snapshots, and export the results. An enrolled
coach or referee reviews under a study code tied to their login: the server
hands them one step at a time (`services.reliance.next_step`) and never sends an
advisory's correctness, its session, or which time point a check-in is.

Offline review of recorded sessions only — not a live decision-support path.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, require_researcher, require_viewer
from api.deps import db_session
from api.services import reliance
from coach import WITHHELD, find_blocked
from store import PayloadModeEnum, Session, User, UserRole
from store.models import (
    AdviceCorrectnessEnum,
    RelianceDecisionEnum,
    RelianceTrialRow,
    StudyAdviceClaimRow,
    StudyAdviceSnapshotRow,
    StudyReviewerRow,
    TraceOpenEventRow,
    TrustSurveyRow,
)

router = APIRouter(prefix="/v2/studies/reliance", tags=["studies"])

_REVIEWER_ROLES = {UserRole.COACH, UserRole.REFEREE}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_reviewer(
    viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> StudyReviewerRow:
    row = db.exec(
        select(StudyReviewerRow).where(StudyReviewerRow.user_id == viewer.user.id)
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You're not enrolled in this study — a researcher enrols you once your consent form is signed.",
        )
    return row


# --------------------------------------------------------------------------
# Researchers
# --------------------------------------------------------------------------


class Item(BaseModel):
    id: str
    text: str


class InstrumentOut(BaseModel):
    name: str
    ready: bool  # False while the protocol's wording hasn't been pasted in
    scale: dict[str, Any]
    trust: list[Item]
    distrust: list[Item]


def _instrument_out() -> InstrumentOut:
    ins = reliance.instrument()
    return InstrumentOut(
        name=ins.name,
        ready=ins.ready,
        scale=ins.scale,
        trust=[Item(**i) for i in ins.trust],
        distrust=[Item(**i) for i in ins.distrust],
    )


@router.get("/instrument", response_model=InstrumentOut)
def get_instrument(_: Viewer = Depends(require_researcher)) -> InstrumentOut:
    return _instrument_out()


class EnrolIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class ReviewerOut(BaseModel):
    reviewer_code: str
    name: str
    email: str
    role: str
    enrolled_at: str
    decisions: int
    check_ins: int


def _reviewer_out(db: DBSession, r: StudyReviewerRow) -> ReviewerOut:
    user = db.get(User, r.user_id)
    n_trials = len(
        db.exec(
            select(RelianceTrialRow.id).where(RelianceTrialRow.reviewer_code == r.reviewer_code)
        ).all()
    )
    n_surveys = len(
        db.exec(
            select(TrustSurveyRow.id).where(TrustSurveyRow.reviewer_code == r.reviewer_code)
        ).all()
    )
    return ReviewerOut(
        reviewer_code=r.reviewer_code,
        name=user.name if user else "—",
        email=user.email if user else "—",
        role=str(user.role) if user else "—",
        enrolled_at=r.enrolled_at.isoformat(),
        decisions=n_trials,
        check_ins=n_surveys,
    )


@router.get("/reviewers", response_model=list[ReviewerOut])
def list_reviewers(
    _: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> list[ReviewerOut]:
    rows = db.exec(select(StudyReviewerRow).order_by(col(StudyReviewerRow.enrolled_at))).all()
    return [_reviewer_out(db, r) for r in rows]


@router.post("/reviewers", response_model=ReviewerOut, status_code=status.HTTP_201_CREATED)
def enrol_reviewer(
    body: EnrolIn, viewer: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> ReviewerOut:
    """Enrol a coach or referee account — only once their signed consent is checked."""
    user = db.exec(select(User).where(func.lower(User.email) == body.email.strip().lower())).first()
    if user is None:
        raise HTTPException(status_code=404, detail="No account with that email")
    if user.role not in _REVIEWER_ROLES:
        raise HTTPException(status_code=422, detail="Reviewers are coach or referee accounts")
    if db.exec(select(StudyReviewerRow).where(StudyReviewerRow.user_id == user.id)).first():
        raise HTTPException(status_code=409, detail="Already enrolled")
    row = StudyReviewerRow(
        user_id=user.id, reviewer_code=reliance.next_code(db), enrolled_by=viewer.user.id
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _reviewer_out(db, row)


class ClaimIn(BaseModel):
    claim_text: str = Field(min_length=1)
    evidence: dict[str, Any]
    source_stream: str = Field(min_length=1, max_length=40)
    source_start_ms: float | None = Field(default=None, ge=0)
    source_end_ms: float | None = Field(default=None, ge=0)
    evidence_quality: str = Field(min_length=1, max_length=40)


class SnapshotIn(BaseModel):
    session_id: UUID
    payload_mode: PayloadModeEnum
    model_id: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=40)
    prompt_text: str = Field(min_length=1)
    input_payload: dict[str, Any]
    summary: str = Field(min_length=1)
    action_items: list[str] = Field(min_length=1, max_length=3)
    correctness: AdviceCorrectnessEnum
    adjudication_note: str = Field(min_length=1)
    claims: list[ClaimIn] = Field(min_length=1)


class SnapshotIndexItem(BaseModel):
    id: UUID
    session_id: UUID
    payload_mode: PayloadModeEnum
    model_id: str
    prompt_version: str
    correctness: str  # researchers only: they adjudicated it
    claims: int
    output_sha256: str
    created_at: str


def _claims(db: DBSession, snapshot_id: UUID) -> list[StudyAdviceClaimRow]:
    return list(
        db.exec(
            select(StudyAdviceClaimRow)
            .where(StudyAdviceClaimRow.snapshot_id == snapshot_id)
            .order_by(col(StudyAdviceClaimRow.ordinal))
        ).all()
    )


@router.get("/snapshots", response_model=list[SnapshotIndexItem])
def list_snapshots(
    _: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> list[SnapshotIndexItem]:
    rows = db.exec(
        select(StudyAdviceSnapshotRow).order_by(col(StudyAdviceSnapshotRow.created_at))
    ).all()
    return [
        SnapshotIndexItem(
            id=s.id,
            session_id=s.session_id,
            payload_mode=s.payload_mode,
            model_id=s.model_id,
            prompt_version=s.prompt_version,
            correctness=str(s.correctness),
            claims=len(_claims(db, s.id)),
            output_sha256=s.output_sha256,
            created_at=s.created_at.isoformat(),
        )
        for s in rows
    ]


class SnapshotCreated(BaseModel):
    id: UUID
    input_sha256: str
    output_sha256: str


@router.post("/snapshots", response_model=SnapshotCreated, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    body: SnapshotIn,
    viewer: Viewer = Depends(require_researcher),
    db: DBSession = Depends(db_session),
) -> SnapshotCreated:
    """Freeze an adjudicated advisory, split into claims with their evidence, before
    any reviewer sees it. Immutable: there is no edit or delete."""
    if db.get(Session, body.session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    # Study advice is training advice too (ADR-039): nothing medical reaches reviewers.
    blocked = find_blocked(body.summary, *body.action_items, *(c.claim_text for c in body.claims))
    if blocked:
        raise HTTPException(
            status_code=422,
            detail=f"This advice reads as medical ({', '.join(blocked)}): the study shows "
            "training advice only. Reword it without these.",
        )
    input_json = _canonical(body.input_payload)
    advice_json = _canonical({"summary": body.summary, "action_items": body.action_items})
    snap = StudyAdviceSnapshotRow(
        session_id=body.session_id,
        payload_mode=body.payload_mode,
        model_id=body.model_id,
        prompt_version=body.prompt_version,
        input_json=input_json,
        advice_json=advice_json,
        input_sha256=_sha256(input_json),
        prompt_sha256=_sha256(body.prompt_text),
        output_sha256=_sha256(advice_json),
        correctness=body.correctness,
        adjudication_note=body.adjudication_note,
        created_by=viewer.user.id,
    )
    db.add(snap)
    db.flush()
    for ordinal, c in enumerate(body.claims):
        db.add(
            StudyAdviceClaimRow(
                snapshot_id=snap.id,
                ordinal=ordinal,
                claim_text=c.claim_text,
                evidence_json=_canonical(c.evidence),
                source_stream=c.source_stream,
                source_start_ms=c.source_start_ms,
                source_end_ms=c.source_end_ms,
                evidence_quality=c.evidence_quality,
            )
        )
    db.commit()
    return SnapshotCreated(
        id=snap.id, input_sha256=snap.input_sha256, output_sha256=snap.output_sha256
    )


class TrialRecord(BaseModel):
    reviewer_code: str
    position: int
    snapshot_id: UUID
    payload_mode: str
    correctness: str
    decision: str
    reliance: str  # appropriate_reliance | appropriate_self_reliance | over_reliance | …
    response_ms: int
    claims: int
    evidence_opened: int  # how many of its claims' evidence the reviewer opened
    rationale: str | None
    submitted_at: str


class SurveyRecord(BaseModel):
    reviewer_code: str
    timepoint: str
    after_trials: int
    trust_score: float
    distrust_score: float
    items: dict[str, Any]
    submitted_at: str


class ExportOut(BaseModel):
    instrument: str
    reviewers: int
    trials: list[TrialRecord]
    surveys: list[SurveyRecord]


@router.get("/export", response_model=ExportOut)
def export(
    _: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> ExportOut:
    """Everything the analysis needs, by reviewer code — no names (H1–H3)."""
    snaps = {s.id: s for s in db.exec(select(StudyAdviceSnapshotRow)).all()}
    claims_of: dict[UUID, list[UUID]] = {}
    for c in db.exec(select(StudyAdviceClaimRow)).all():
        claims_of.setdefault(c.snapshot_id, []).append(c.id)
    opens = {(o.claim_id, o.reviewer_code) for o in db.exec(select(TraceOpenEventRow)).all()}
    trials = db.exec(
        select(RelianceTrialRow).order_by(
            col(RelianceTrialRow.reviewer_code), col(RelianceTrialRow.position)
        )
    ).all()
    out_trials = []
    for t in trials:
        s = snaps[t.snapshot_id]
        ids = claims_of.get(t.snapshot_id, [])
        out_trials.append(
            TrialRecord(
                reviewer_code=t.reviewer_code,
                position=t.position,
                snapshot_id=t.snapshot_id,
                payload_mode=str(s.payload_mode),
                correctness=str(s.correctness),
                decision=str(t.decision),
                reliance=reliance.classify(str(s.correctness), str(t.decision)),
                response_ms=t.response_ms,
                claims=len(ids),
                evidence_opened=sum(1 for cid in ids if (cid, t.reviewer_code) in opens),
                rationale=t.rationale,
                submitted_at=t.submitted_at.isoformat(),
            )
        )
    surveys = db.exec(
        select(TrustSurveyRow).order_by(
            col(TrustSurveyRow.reviewer_code), col(TrustSurveyRow.after_trials)
        )
    ).all()
    return ExportOut(
        instrument=reliance.instrument().name,
        reviewers=len(db.exec(select(StudyReviewerRow.id)).all()),
        trials=out_trials,
        surveys=[
            SurveyRecord(
                reviewer_code=v.reviewer_code,
                timepoint=str(v.timepoint),
                after_trials=v.after_trials,
                trust_score=v.trust_score,
                distrust_score=v.distrust_score,
                items=json.loads(v.item_scores_json),
                submitted_at=v.submitted_at.isoformat(),
            )
            for v in surveys
        ],
    )


# --------------------------------------------------------------------------
# Reviewers
# --------------------------------------------------------------------------


class ClaimOut(BaseModel):
    id: UUID
    claim_text: str
    evidence: dict[str, Any]
    source_stream: str
    source_start_ms: float | None
    source_end_ms: float | None
    evidence_quality: str


class AdvisoryOut(BaseModel):
    """What a reviewer sees: the advice and its evidence — no correctness, no session."""

    id: UUID
    summary: str
    action_items: list[str]
    claims: list[ClaimOut]


class StepOut(BaseModel):
    kind: str  # "survey" | "trial" | "done"
    label: str  # neutral: "Check-in 2", "Advisory 3 of 8"
    advisory: AdvisoryOut | None = None
    instrument: InstrumentOut | None = None


class MeOut(BaseModel):
    reviewer_code: str
    ready: bool  # the questionnaire's wording is in place
    decisions: int
    total: int
    step: StepOut


def _advisory(db: DBSession, s: StudyAdviceSnapshotRow) -> AdvisoryOut:
    advice = json.loads(s.advice_json)
    claims = _claims(db, s.id)
    if find_blocked(advice["summary"], *advice["action_items"], *(c.claim_text for c in claims)):
        # Checked again when shown (ADR-039): a term added later still stops it.
        return AdvisoryOut(id=s.id, summary=WITHHELD, action_items=[], claims=[])
    return AdvisoryOut(
        id=s.id,
        summary=advice["summary"],
        action_items=advice["action_items"],
        claims=[
            ClaimOut(
                id=c.id,
                claim_text=c.claim_text,
                evidence=json.loads(c.evidence_json),
                source_stream=c.source_stream,
                source_start_ms=c.source_start_ms,
                source_end_ms=c.source_end_ms,
                evidence_quality=c.evidence_quality,
            )
            for c in claims
        ],
    )


@router.get("/me", response_model=MeOut)
def my_step(
    me: StudyReviewerRow = Depends(require_reviewer), db: DBSession = Depends(db_session)
) -> MeOut:
    """The reviewer's next step, chosen by the server."""
    ready = reliance.instrument().ready
    step = reliance.next_step(db, me.reviewer_code)
    if step.kind == "survey":
        out = StepOut(
            kind="survey", label=f"Check-in {step.surveys_done + 1}", instrument=_instrument_out()
        )
    elif step.kind == "trial" and step.snapshot is not None:
        out = StepOut(
            kind="trial",
            label=f"Advisory {step.position} of {step.total}",
            advisory=_advisory(db, step.snapshot),
        )
    else:
        out = StepOut(kind="done", label="All done")
    return MeOut(
        reviewer_code=me.reviewer_code,
        ready=ready,
        decisions=_decisions(db, me.reviewer_code),
        total=step.total,
        step=out,
    )


def _decisions(db: DBSession, code: str) -> int:
    return len(
        db.exec(select(RelianceTrialRow.id).where(RelianceTrialRow.reviewer_code == code)).all()
    )


def _require_ready() -> None:
    if not reliance.instrument().ready:
        raise HTTPException(
            status_code=409, detail="The study isn't open yet: the questionnaire wording is missing"
        )


class SurveyIn(BaseModel):
    trust_items: dict[str, int]
    distrust_items: dict[str, int]


@router.post("/surveys", status_code=status.HTTP_201_CREATED)
def submit_survey(
    body: SurveyIn,
    me: StudyReviewerRow = Depends(require_reviewer),
    db: DBSession = Depends(db_session),
) -> dict[str, bool]:
    """The check-in that's due — the server knows which time point it is."""
    _require_ready()
    step = reliance.next_step(db, me.reviewer_code)
    if step.kind != "survey" or step.timepoint is None:
        raise HTTPException(status_code=409, detail="No check-in is due")
    ins = reliance.instrument()
    lo, hi = int(ins.scale["min"]), int(ins.scale["max"])
    trust_ids, distrust_ids = ins.ids()
    if set(body.trust_items) != trust_ids or set(body.distrust_items) != distrust_ids:
        raise HTTPException(status_code=422, detail="Answer every item of the questionnaire")
    if any(not lo <= v <= hi for v in [*body.trust_items.values(), *body.distrust_items.values()]):
        raise HTTPException(status_code=422, detail=f"Items use the {lo}–{hi} scale")
    db.add(
        TrustSurveyRow(
            reviewer_code=me.reviewer_code,
            timepoint=step.timepoint,
            after_trials=_decisions(db, me.reviewer_code),
            item_scores_json=_canonical(
                {"trust_items": body.trust_items, "distrust_items": body.distrust_items}
            ),
            trust_score=reliance.scores(body.trust_items),
            distrust_score=reliance.scores(body.distrust_items),
        )
    )
    db.commit()
    return {"recorded": True}


def _due_trial(db: DBSession, code: str) -> reliance.Step:
    step = reliance.next_step(db, code)
    if step.kind != "trial" or step.snapshot is None:
        raise HTTPException(status_code=409, detail="No advisory is due")
    return step


@router.post("/claims/{claim_id}/trace-opens", status_code=status.HTTP_201_CREATED)
def record_trace_open(
    claim_id: UUID,
    me: StudyReviewerRow = Depends(require_reviewer),
    db: DBSession = Depends(db_session),
) -> dict[str, bool]:
    """The reviewer opened a claim's evidence — logged once, on the advisory in front of them."""
    claim = db.get(StudyAdviceClaimRow, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    step = _due_trial(db, me.reviewer_code)
    if step.snapshot is None or claim.snapshot_id != step.snapshot.id:
        raise HTTPException(
            status_code=409, detail="That claim isn't on the advisory in front of you"
        )
    seen = db.exec(
        select(TraceOpenEventRow).where(
            TraceOpenEventRow.claim_id == claim_id,
            TraceOpenEventRow.reviewer_code == me.reviewer_code,
        )
    ).first()
    if seen is None:
        db.add(TraceOpenEventRow(claim_id=claim_id, reviewer_code=me.reviewer_code))
        db.commit()
    return {"recorded": True}


class TrialIn(BaseModel):
    decision: RelianceDecisionEnum
    response_ms: int = Field(ge=0, le=3_600_000)
    rationale: str | None = Field(default=None, max_length=2_000)


@router.post("/snapshots/{snapshot_id}/trials", status_code=status.HTTP_201_CREATED)
def record_trial(
    snapshot_id: UUID,
    body: TrialIn,
    me: StudyReviewerRow = Depends(require_reviewer),
    db: DBSession = Depends(db_session),
) -> dict[str, bool]:
    """Follow, adjust or reject the advisory that's due — final once sent."""
    _require_ready()
    step = _due_trial(db, me.reviewer_code)
    if step.snapshot is None or step.snapshot.id != snapshot_id:
        raise HTTPException(status_code=409, detail="That isn't the advisory that's due")
    db.add(
        RelianceTrialRow(
            snapshot_id=snapshot_id,
            reviewer_code=me.reviewer_code,
            position=step.position,
            decision=body.decision,
            response_ms=body.response_ms,
            rationale=(body.rationale or "").strip() or None,
        )
    )
    db.commit()
    return {"recorded": True}
