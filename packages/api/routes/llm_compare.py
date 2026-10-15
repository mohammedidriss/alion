"""Saved language-model comparisons (ADR-058), for researchers.

POST /v2/llm/comparisons                     start one: {models: [{choice, model}], session_ids, repeats}
GET  /v2/llm/comparisons                     every comparison, newest first
GET  /v2/llm/comparisons/{id}                its progress, a summary per model, and every trial
POST /v2/llm/comparisons/{id}/stop           stop it after the trial in hand
POST /v2/llm/comparisons/{id}/reveal         show the models' names (later ratings aren't blind)
PUT  /v2/llm/comparisons/{id}/ratings/{tid}  rate one trial's cards 1–5
GET  /v2/llm/comparisons/{id}/csv            every trial as a CSV row

A comparison runs on the server, one request at a time so timings aren't shared,
and keeps going if the page is left: each model is woken first (untimed), then
phrases the rest cards of every round of every session, as many times as asked
(`run_trial` — the rest minute's facts, prompt and verifier). Each model has a
blind code (A, B, …): until someone reveals the names, the results and the cards
show the code only, so the cards can be rated on their merit. Nothing here is
shown to a coach or recorded as advice.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import random
import statistics
import threading
from collections import Counter, defaultdict
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api import access
from api.deps import db_session
from api.routes.llm import _setup, run_trial
from coach.llm_client import ping
from common import get_logger, llm_setups
from store import LlmComparison, LlmRating, LlmTrialResult, get_session

log = get_logger(__name__)
router = APIRouter(prefix="/v2/llm/comparisons", tags=["llm"])

BACKGROUND = True  # tests switch the thread off and the comparison runs in the request
MAX_MODELS = 4
MAX_SESSIONS = 5
MAX_REPEATS = 3
MAX_ROUNDS = 12
CODES = "ABCD"

_lock = threading.Lock()
_running: set[UUID] = set()
_stop: set[UUID] = set()


class ModelIn(BaseModel):
    choice: str
    model: str


class ComparisonIn(BaseModel):
    models: list[ModelIn] = Field(min_length=1, max_length=MAX_MODELS)
    session_ids: list[UUID] = Field(min_length=1, max_length=MAX_SESSIONS)
    repeats: int = Field(default=1, ge=1, le=MAX_REPEATS)


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)


def _models(c: LlmComparison) -> list[dict[str, str]]:
    return list(json.loads(c.models))


def _sessions(c: LlmComparison) -> list[dict[str, Any]]:
    return list(json.loads(c.session_ids))


def _step(db: DBSession, c: LlmComparison, text: str) -> None:
    c.step = text[:200]
    db.add(c)
    db.commit()


def _run(cid: UUID, db: DBSession | None = None) -> None:
    """Run the comparison's trials in order: model by model (woken first, untimed),
    repeat by repeat, session by session, round by round."""
    gen: Generator[DBSession, None, None] | None = None
    if db is None:
        own: Generator[DBSession, None, None] = get_session()  # type: ignore[assignment]
        gen, db = own, next(own)
    assert db is not None
    c = db.get(LlmComparison, cid)
    if c is None:
        return
    try:
        sessions = _sessions(c)
        for m in _models(c):
            setup = llm_setups.setups().get(m["choice"])
            if setup is not None:
                _step(db, c, f"Waking model {m['code']} (not timed)…")
                asyncio.run(ping(setup.url, setup.api_key, m["model"]))
            for rep in range(1, c.repeats + 1):
                for k, s in enumerate(sessions, 1):
                    for rnd in range(1, int(s["rounds"]) + 1):
                        if cid in _stop:
                            c.status = "stopped"
                            return
                        _step(
                            db,
                            c,
                            f"Model {m['code']} — session {k} of {len(sessions)}, "
                            f"round {rnd} of {s['rounds']}, run {rep} of {c.repeats}",
                        )
                        db.add(_trial(db, m, setup, UUID(s["id"]), rnd, rep, cid))
                        db.commit()
        c.status = "done"
    except Exception as e:  # recorded, not raised: the thread has nobody to tell
        log.exception("llm_compare.failed", extra={"_ctx_comparison": str(cid)})
        c.status = "failed"
        c.step = f"Failed: {e}"[:200]
    finally:
        c.finished_at = datetime.now(UTC)
        if c.status == "running":
            c.status = "done"
        db.add(c)
        db.commit()
        with _lock:
            _running.discard(cid)
            _stop.discard(cid)
        if gen is not None:
            gen.close()


def _trial(
    db: DBSession,
    m: dict[str, str],
    setup: llm_setups.LlmSetup | None,
    session_id: UUID,
    rnd: int,
    rep: int,
    cid: UUID,
) -> LlmTrialResult:
    row = LlmTrialResult(
        comparison_id=cid,
        code=m["code"],
        choice=m["choice"],
        model=m["model"],
        session_id=session_id,
        after_round=rnd,
        repeat=rep,
    )
    if setup is None:
        row.detail = json.dumps({"error": f"No '{m['choice']}' AI is configured any more"})
        return row
    try:
        out = asyncio.run(run_trial(db, setup, m["model"], session_id, rnd))
    except HTTPException as e:
        row.detail = json.dumps({"error": str(e.detail)})
        return row
    except Exception as e:
        row.detail = json.dumps({"error": str(e)[:300]})
        return row
    row.seconds = out["seconds"]
    row.answered = bool(out["answered"])
    row.in_time = bool(out["in_time"])
    row.written = int(out["written"])
    row.passed = int(out["passed"])
    row.detail = json.dumps(
        {k: out[k] for k in ("verdicts", "cards", "blocked_terms", "facts", "round_count")}
    )
    return row


def _settle(db: DBSession, c: LlmComparison) -> LlmComparison:
    """A comparison left "running" with nothing running it (the server restarted
    mid-run) is stopped — its trials so far are kept."""
    with _lock:
        orphan = c.status == "running" and c.id not in _running
    if orphan:
        c.status = "stopped"
        c.step = "Stopped: the server restarted while it ran"
        c.finished_at = datetime.now(UTC)
        db.add(c)
        db.commit()
    return c


def _get(db: DBSession, cid: UUID) -> LlmComparison:
    c = db.get(LlmComparison, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="comparison not found")
    return _settle(db, c)


def _trials(db: DBSession, cid: UUID) -> list[LlmTrialResult]:
    q = select(LlmTrialResult).where(LlmTrialResult.comparison_id == cid)
    return list(db.exec(q.order_by(col(LlmTrialResult.id))).all())


def _ratings(db: DBSession, cid: UUID) -> list[LlmRating]:
    return list(db.exec(select(LlmRating).where(LlmRating.comparison_id == cid)).all())


def _summary(
    m: dict[str, str], rows: list[LlmTrialResult], ratings: list[LlmRating], revealed: bool
) -> dict[str, Any]:
    secs = [r.seconds for r in rows if r.answered and r.seconds is not None]
    gates: Counter[str] = Counter()
    errors = 0
    for r in rows:
        d = json.loads(r.detail or "{}")
        errors += "error" in d
        for v in d.get("verdicts") or []:
            if not v.get("ok") and v.get("gate"):
                gates[str(v["gate"]).split(":")[0]] += 1
    # The same round run more than once: did every run pass as many cards?
    by_round: dict[tuple[UUID, int], list[int]] = defaultdict(list)
    for r in rows:
        if r.answered:
            by_round[(r.session_id, r.after_round)].append(r.passed)
    repeated = [v for v in by_round.values() if len(v) > 1]
    ids = {r.id for r in rows}
    mine = [x for x in ratings if x.trial_id in ids]
    blind = [x.score for x in mine if x.blind]
    out: dict[str, Any] = {
        "code": m["code"],
        "trials": len(rows),
        "answered": sum(r.answered for r in rows),
        "avg_seconds": round(statistics.fmean(secs), 1) if secs else None,
        "median_seconds": round(statistics.median(secs), 1) if secs else None,
        "slowest_seconds": max(secs) if secs else None,
        "in_time": sum(r.in_time for r in rows),
        "written": sum(r.written for r in rows),
        "passed": sum(r.passed for r in rows),
        "slots": 3 * len(rows),
        "top_gate": gates.most_common(1)[0][0] if gates else None,
        "errors": errors,
        "consistent": (
            round(sum(len(set(v)) == 1 for v in repeated) / len(repeated), 2) if repeated else None
        ),
        "rating": round(statistics.fmean(x.score for x in mine), 2) if mine else None,
        "blind_rating": round(statistics.fmean(blind), 2) if blind else None,
        "ratings": len(mine),
    }
    if revealed:
        active = llm_setups.active()
        out |= {
            "choice": m["choice"],
            "model": m["model"],
            "label": m.get("label"),
            "in_use": bool(active and active.name == m["choice"] and active.model == m["model"]),
        }
    return out


def _out(db: DBSession, c: LlmComparison, viewer: access.Viewer, *, trials: bool) -> dict[str, Any]:
    rows = _trials(db, c.id)
    ratings = _ratings(db, c.id)
    revealed = c.revealed_at is not None
    models = _models(c)
    out: dict[str, Any] = {
        "id": str(c.id),
        "created_at": c.created_at.isoformat(),
        "finished_at": c.finished_at.isoformat() if c.finished_at else None,
        "status": c.status,
        "step": c.step,
        "done": len(rows),
        "total": c.total,
        "repeats": c.repeats,
        "sessions": _sessions(c),
        "revealed": revealed,
        "models": [
            _summary(m, [r for r in rows if r.code == m["code"]], ratings, revealed) for m in models
        ],
    }
    if trials:
        mine = {x.trial_id: x.score for x in ratings if x.rater_id == viewer.user.id}
        out["trials"] = [
            {
                "id": r.id,
                "code": r.code,
                **({"model": r.model} if revealed else {}),
                "session_id": str(r.session_id),
                "after_round": r.after_round,
                "repeat": r.repeat,
                "seconds": r.seconds,
                "answered": r.answered,
                "in_time": r.in_time,
                "written": r.written,
                "passed": r.passed,
                "detail": json.loads(r.detail or "{}"),
                "my_score": mine.get(r.id or 0),
            }
            for r in rows
        ]
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def start_comparison(
    body: ComparisonIn,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    """Check the models and sessions, save the plan, and run it."""
    from api.routes import rest_cards as rc

    keys = [(m.choice, m.model) for m in body.models]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=422, detail="Each model once")
    models = []
    # A, B, … handed out in a shuffled order: the code doesn't say which model it is.
    shuffled = random.sample(body.models, len(body.models))
    for code, m in zip(CODES, shuffled, strict=False):
        setup = _setup(m.choice, m.model)  # configured, allowed, installed
        models.append({"code": code, "choice": m.choice, "model": m.model, "label": setup.label})
    models.sort(key=lambda m: m["code"])
    sessions = []
    for sid in dict.fromkeys(body.session_ids):
        row = rc._gate(db, sid)  # 404, and the coach-only study condition
        viewer.require(row.fighter_id, access.Level.TRAINING)
        rounds = min(row.round_count or 0, MAX_ROUNDS)
        if rounds < 1:
            raise HTTPException(status_code=422, detail="Pick sessions with rounds")
        sessions.append(
            {"id": str(sid), "rounds": rounds, "started_at": row.started_at.isoformat()}
        )
    with _lock:
        if _running:
            raise HTTPException(status_code=409, detail="A comparison is running — stop it or wait")
    total = len(models) * body.repeats * sum(int(s["rounds"]) for s in sessions)
    c = LlmComparison(
        created_by=viewer.user.id,
        models=json.dumps(models),
        session_ids=json.dumps(sessions),
        repeats=body.repeats,
        total=total,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    with _lock:
        _running.add(c.id)
    if BACKGROUND:
        threading.Thread(target=_run, args=(c.id,), daemon=True).start()
    else:
        _run(c.id, db)
        db.refresh(c)
    return _out(db, c, viewer, trials=False)


@router.get("")
def list_comparisons(
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = db.exec(select(LlmComparison).order_by(col(LlmComparison.created_at).desc())).all()
    return [_out(db, _settle(db, c), viewer, trials=False) for c in rows]


@router.get("/{cid}")
def get_comparison(
    cid: UUID,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    return _out(db, _get(db, cid), viewer, trials=True)


@router.post("/{cid}/stop")
def stop_comparison(
    cid: UUID,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    c = _get(db, cid)
    with _lock:
        if cid in _running:
            _stop.add(cid)
    return _out(db, c, viewer, trials=False)


@router.post("/{cid}/reveal")
def reveal(
    cid: UUID,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    """Show which model is which. Ratings given from now on are marked not blind."""
    c = _get(db, cid)
    if c.revealed_at is None:
        c.revealed_at = datetime.now(UTC)
        db.add(c)
        db.commit()
    return _out(db, c, viewer, trials=True)


@router.put("/{cid}/ratings/{trial_id}")
def rate(
    cid: UUID,
    trial_id: int,
    body: RatingIn,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    """Rate a trial's cards: how useful they'd be to a coach in the rest minute."""
    c = _get(db, cid)
    trial = db.get(LlmTrialResult, trial_id)
    if trial is None or trial.comparison_id != cid:
        raise HTTPException(status_code=404, detail="No such trial in this comparison")
    row = db.exec(
        select(LlmRating).where(
            LlmRating.trial_id == trial_id, LlmRating.rater_id == viewer.user.id
        )
    ).first() or LlmRating(
        comparison_id=cid, trial_id=trial_id, rater_id=viewer.user.id, score=body.score
    )
    row.score = body.score
    row.blind = c.revealed_at is None
    row.created_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    return {"trial_id": trial_id, "score": row.score, "blind": row.blind}


@router.get("/{cid}/csv")
def export_csv(
    cid: UUID,
    viewer: access.Viewer = Depends(access.require_researcher),
    db: DBSession = Depends(db_session),
) -> Response:
    """Every trial as a row — the model's name only once revealed — with its mean
    rating, for analysis outside Alion."""
    c = _get(db, cid)
    revealed = c.revealed_at is not None
    ratings = _ratings(db, cid)
    by_trial: dict[int, list[LlmRating]] = defaultdict(list)
    for rating in ratings:
        by_trial[rating.trial_id].append(rating)
    started = {UUID(s["id"]): s.get("started_at") for s in _sessions(c)}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "comparison", "code", "setup", "model", "session", "session_started", "after_round",
            "repeat", "seconds", "answered", "in_time", "cards_written", "cards_passed",
            "blocked_terms", "failed_gates", "error", "rating_mean", "ratings", "ratings_blind",
        ]
    )  # fmt: skip
    for r in _trials(db, cid):
        d = json.loads(r.detail or "{}")
        rs = by_trial.get(r.id or 0, [])
        w.writerow(
            [
                c.id, r.code, r.choice if revealed else "", r.model if revealed else "",
                r.session_id, started.get(r.session_id, ""), r.after_round, r.repeat,
                r.seconds if r.seconds is not None else "", int(r.answered), int(r.in_time),
                r.written, r.passed, "|".join(d.get("blocked_terms") or []),
                "|".join(str(v.get("gate")) for v in d.get("verdicts") or [] if not v.get("ok")),
                d.get("error", ""),
                round(statistics.fmean(x.score for x in rs), 2) if rs else "",
                len(rs), sum(x.blind for x in rs),
            ]
        )  # fmt: skip
    name = f"llm-comparison-{c.created_at.date().isoformat()}-{str(c.id)[:8]}.csv"
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
