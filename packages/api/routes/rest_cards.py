"""Rest cards (ADR-041, ADR-043): three cards for the minute between rounds.

GET  /sessions/{id}/rest_cards?after_round=N[&live=true]   the facts and template cards
POST /sessions/{id}/rest_cards                              …and a model's phrasing, verified
POST /sessions/{id}/rest_cards/feedback                     a coach's "noted", "dismissed",
                                                            or own read before the cards
GET  /sessions/{id}/rest_cards/feedback                     what was logged

The template cards come from fixed rules over the facts ledger and are ready at
once. The POST also asks the language model to phrase them; each model card is
checked against the ledger (`coach.verify`) and replaces its template only if it
passes. Every POST is recorded with the ledger's hash, the model's output and a
verdict per card (`advice_gate`).
"""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, require_viewer
from api.deps import db_session, punch_event_repo, session_repo
from api.routes import capture_coord
from api.routes.auth import require_current_user
from api.services import advice_gate, hrv_runner, rest_cards
from api.services.rest_cards import Card, Fact
from store import CardFeedbackRow, PunchEventRepo, SessionRepo

router = APIRouter(
    prefix="/sessions",
    tags=["rest-cards"],
    dependencies=[Depends(require_current_user)],
)

PHRASE_TIMEOUT_S = 12.0  # the cards are on screen already; the phrasing may not come


class RestCardsOut(BaseModel):
    after_round: int
    round_count: int
    live: bool
    facts: list[Fact]
    facts_sha256: str
    cards: list[Card]
    verdicts: list[dict[str, Any]] | None = None  # the model's cards, gate by gate
    model: str | None = None
    advice_id: UUID | None = None


class RestCardsIn(BaseModel):
    after_round: int = Field(ge=1)
    live: bool = False


def _gate(db: DBSession, session_id: UUID) -> Any:
    from store import Session as SessionRow
    from store import StudyConditionEnum

    row = db.get(SessionRow, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if (
        row.study_condition is not None
        and not StudyConditionEnum(row.study_condition).allows_ai_advice
    ):
        raise HTTPException(
            status_code=403,
            detail=f"No system advice for study condition '{row.study_condition}' (coach-only control).",
        )
    return row


def _live_rest(session_id: UUID) -> dict[str, float] | None:
    """How far into the current pause, and the heart rate now (mean of the last 5)."""
    pause = capture_coord.pause_at_ms(session_id, capture_coord._now_ms())
    bpm = hrv_runner.recent_bpm(session_id)[-5:]
    if pause is None or not bpm:
        return None
    return {"elapsed_s": pause[2] / 1000.0, "hr_now": sum(bpm) / len(bpm)}


def _ledger(
    session_id: UUID,
    after_round: int,
    live: bool,
    sessions: SessionRepo,
    events: PunchEventRepo,
    db: DBSession,
) -> tuple[Any, list[Fact]]:
    from api.routes.sessions import rounds_export

    ex = rounds_export(session_id, sessions, events, db)
    if after_round > ex.round_count:
        raise HTTPException(status_code=422, detail=f"the plan has {ex.round_count} rounds")
    facts = rest_cards.build_facts(ex, after_round, _live_rest(session_id) if live else None)
    return ex, facts


@router.get("/{session_id}/rest_cards", response_model=RestCardsOut)
def get_rest_cards(
    session_id: UUID,
    after_round: int,
    live: bool = False,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> RestCardsOut:
    """The facts after round N and the three template cards — no model, at once."""
    _gate(db, session_id)
    if after_round < 1:
        raise HTTPException(status_code=422, detail="after_round starts at 1")
    ex, facts = _ledger(session_id, after_round, live, sessions, events, db)
    return RestCardsOut(
        after_round=after_round,
        round_count=ex.round_count,
        live=live,
        facts=facts,
        facts_sha256=rest_cards.facts_sha256(facts),
        cards=rest_cards.template_cards(facts),
    )


@router.post("/{session_id}/rest_cards", response_model=RestCardsOut)
async def phrase_rest_cards(
    session_id: UUID,
    body: RestCardsIn,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
    viewer: Viewer = Depends(require_viewer),
) -> RestCardsOut:
    """The template cards, each replaced by the model's phrasing where it passes
    every gate of the verifier. Recorded either way."""
    from coach import PROMPT_VERSION, REST_CARDS_SYSTEM_PROMPT, generate_json
    from coach.llm_client import llm_config
    from coach.verify import verify_cards

    row = _gate(db, session_id)
    ex, facts = _ledger(session_id, body.after_round, body.live, sessions, events, db)
    templates = rest_cards.template_cards(facts)
    sha = rest_cards.facts_sha256(facts)
    payload = json.dumps(
        {
            "round": body.after_round,
            "stance": ex.stance,
            "facts": [f.model_dump() for f in facts],
            "suggested": {c.slot: c.fact_ids for c in templates if c.fact_ids},
        }
    )
    output = (
        await generate_json(REST_CARDS_SYSTEM_PROMPT, payload, _SCHEMA, timeout_s=PHRASE_TIMEOUT_S)
        if facts
        else None
    )
    passed, verdicts = (
        verify_cards(output, [f.model_dump() for f in facts]) if output is not None else ({}, [])
    )
    by_id = {f.id: f for f in facts}
    shown: list[Card] = []
    for t in templates:
        m = passed.get(t.slot)
        if m is None:
            shown.append(t)
            continue
        cited = [by_id[str(i)] for i in m["cites"]]
        shown.append(
            Card(
                slot=t.slot,
                shape=t.shape,
                headline=str(m["headline"]).strip(),
                number=None,
                context=str(m.get("detail") or "").strip() or None,
                fact_ids=[f.id for f in cited],
                confidence=min(4, max(1, round(4 * min(f.quality for f in cited)))),
                streams=sorted({s for f in cited for s in f.streams}),
                source="model",
            )
        )
    rec = advice_gate.record(
        db,
        kind="rest_cards",
        system_prompt=REST_CARDS_SYSTEM_PROMPT,
        prompt_version=PROMPT_VERSION,
        user_content=payload,
        output={
            "facts_sha256": sha,
            "model_output": output,
            "verdicts": verdicts,
            "shown": [c.model_dump() for c in shown],
        },
        failed=output is None,
        session_id=session_id,
        fighter_id=row.fighter_id,
        payload_mode="rest",
        user_id=viewer.user.id,
    )
    # A blocked term anywhere in what's recorded withholds the model's cards.
    if rec.status == "withheld":
        shown = templates
    return RestCardsOut(
        after_round=body.after_round,
        round_count=ex.round_count,
        live=body.live,
        facts=facts,
        facts_sha256=sha,
        cards=shown,
        verdicts=verdicts or None,
        model=llm_config()[2] if output is not None else None,
        advice_id=rec.id,
    )


_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "slot": {"type": "string", "enum": ["opportunity", "warning", "recovery"]},
        "headline": {"type": "string"},
        "detail": {"type": "string"},
        "cites": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
    "required": ["slot", "headline", "detail", "cites"],
    "additionalProperties": False,
}
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"cards": {"type": "array", "items": _CARD_SCHEMA, "maxItems": 3}},
    "required": ["cards"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# What the coach did with them (ADR-043)
# --------------------------------------------------------------------------


class FeedbackIn(BaseModel):
    after_round: int = Field(ge=1)
    slot: Literal["opportunity", "warning", "recovery", "own_read"]
    action: Literal["noted", "dismissed", "own_read"]
    headline: str | None = Field(default=None, max_length=200)
    fact_ids: list[str] = Field(default_factory=list)
    facts_sha256: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class FeedbackOut(FeedbackIn):
    id: int
    created_at: str


@router.post(
    "/{session_id}/rest_cards/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
def add_feedback(
    session_id: UUID,
    body: FeedbackIn,
    db: DBSession = Depends(db_session),
    viewer: Viewer = Depends(require_viewer),
) -> FeedbackOut:
    _gate(db, session_id)
    if (body.action == "own_read") != (body.slot == "own_read"):
        raise HTTPException(status_code=422, detail="an own read goes in its own slot")
    row = CardFeedbackRow(
        session_id=session_id,
        after_round=body.after_round,
        slot=body.slot,
        action=body.action,
        headline=body.headline,
        fact_ids=json.dumps(body.fact_ids),
        facts_sha256=body.facts_sha256,
        note=(body.note or "").strip() or None,
        user_id=viewer.user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _feedback_out(row)


@router.get("/{session_id}/rest_cards/feedback", response_model=list[FeedbackOut])
def list_feedback(session_id: UUID, db: DBSession = Depends(db_session)) -> list[FeedbackOut]:
    rows = db.exec(
        select(CardFeedbackRow)
        .where(CardFeedbackRow.session_id == session_id)
        .order_by(col(CardFeedbackRow.created_at))
    ).all()
    return [_feedback_out(r) for r in rows]


def _feedback_out(r: CardFeedbackRow) -> FeedbackOut:
    return FeedbackOut(
        id=r.id or 0,
        after_round=r.after_round,
        slot=r.slot,  # type: ignore[arg-type]
        action=r.action,  # type: ignore[arg-type]
        headline=r.headline,
        fact_ids=json.loads(r.fact_ids),
        facts_sha256=r.facts_sha256,
        note=r.note,
        created_at=r.created_at.isoformat(),
    )
