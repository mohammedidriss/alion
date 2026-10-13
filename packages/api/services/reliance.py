"""The appropriate-reliance study's sequence and scoring (ADR-026).

The server, not the reviewer, decides what comes next:

1. the opening trust check-in (pre-exposure);
2. every frozen advisory, in an order counterbalanced per reviewer (a stable
   hash of the reviewer code and the advisory id, so a later advisory slots in
   without reshuffling the rest);
3. a check-in right after the first incorrect advisory (post-error), and one
   after `RECOVERY_CORRECT` correct advisories have followed it (post-recovery) —
   or at the end, if the advisories run out first.

Reviewers only see neutral labels ("Check-in 2"); which time point a check-in is
stays on the server, so a label can't give an advisory's correctness away.

The trust questionnaire (Jian et al.'s checklist: distrust and trust items on a
1–7 scale) is read from `reliance_trust_items.json`; until its wording is pasted
in from the approved protocol the study stays closed to reviewers.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session as DBSession
from sqlmodel import col, select

from store.models import (
    AdviceCorrectnessEnum,
    RelianceDecisionEnum,
    RelianceTrialRow,
    StudyAdviceSnapshotRow,
    StudyReviewerRow,
    TrustSurveyRow,
    TrustTimepointEnum,
)

ITEMS_FILE = Path(__file__).with_name("reliance_trust_items.json")
RECOVERY_CORRECT = 2  # correct advisories after the error before the recovery check-in


def _items_file() -> Path:
    return Path(os.environ.get("ALION_TRUST_ITEMS_FILE") or ITEMS_FILE)


@dataclass(frozen=True)
class Instrument:
    name: str
    scale: dict[str, Any]
    trust: list[dict[str, str]]
    distrust: list[dict[str, str]]

    @property
    def ready(self) -> bool:
        """False while any item is still the '[paste …]' placeholder."""
        return all(not i["text"].lstrip().startswith("[") for i in self.trust + self.distrust)

    def ids(self) -> tuple[set[str], set[str]]:
        return {i["id"] for i in self.trust}, {i["id"] for i in self.distrust}


def instrument() -> Instrument:
    raw = json.loads(_items_file().read_text())
    return Instrument(
        name=raw["instrument"], scale=raw["scale"], trust=raw["trust"], distrust=raw["distrust"]
    )


def next_code(db: DBSession) -> str:
    """RV-001, RV-002, … — the next free reviewer code."""
    taken = set(db.exec(select(StudyReviewerRow.reviewer_code)).all())
    n = len(taken) + 1
    while f"RV-{n:03d}" in taken:
        n += 1
    return f"RV-{n:03d}"


def order(code: str, snapshots: list[StudyAdviceSnapshotRow]) -> list[StudyAdviceSnapshotRow]:
    """This reviewer's counterbalanced order: stable per (reviewer, advisory)."""
    return sorted(snapshots, key=lambda s: hashlib.sha256(f"{code}:{s.id}".encode()).hexdigest())


@dataclass(frozen=True)
class Step:
    kind: str  # "survey" | "trial" | "done"
    timepoint: TrustTimepointEnum | None = None  # server-side only
    snapshot: StudyAdviceSnapshotRow | None = None
    position: int = 0  # the advisory's place in this reviewer's sequence (1-based)
    total: int = 0
    surveys_done: int = 0


def next_step(db: DBSession, code: str) -> Step:
    snapshots = order(code, list(db.exec(select(StudyAdviceSnapshotRow)).all()))
    by_id = {s.id: s for s in snapshots}
    trials = list(
        db.exec(
            select(RelianceTrialRow)
            .where(RelianceTrialRow.reviewer_code == code)
            .order_by(col(RelianceTrialRow.position))
        ).all()
    )
    surveys = {
        s.timepoint: s
        for s in db.exec(select(TrustSurveyRow).where(TrustSurveyRow.reviewer_code == code)).all()
    }
    total, n_surveys = len(snapshots), len(surveys)

    def survey(tp: TrustTimepointEnum) -> Step:
        return Step("survey", timepoint=tp, total=total, surveys_done=n_surveys)

    if TrustTimepointEnum.PRE_EXPOSURE not in surveys:
        return survey(TrustTimepointEnum.PRE_EXPOSURE)

    def correctness(t: RelianceTrialRow) -> AdviceCorrectnessEnum | None:
        s = by_id.get(t.snapshot_id)
        return AdviceCorrectnessEnum(s.correctness) if s else None

    first_error = next(
        (t for t in trials if correctness(t) == AdviceCorrectnessEnum.INCORRECT), None
    )
    done_ids = {t.snapshot_id for t in trials}
    remaining = [s for s in snapshots if s.id not in done_ids]
    if first_error is not None:
        if TrustTimepointEnum.POST_ERROR not in surveys:
            return survey(TrustTimepointEnum.POST_ERROR)
        if TrustTimepointEnum.POST_RECOVERY not in surveys:
            recovered = sum(
                1
                for t in trials
                if t.position > first_error.position
                and correctness(t) == AdviceCorrectnessEnum.CORRECT
            )
            if recovered >= RECOVERY_CORRECT or not remaining:
                return survey(TrustTimepointEnum.POST_RECOVERY)
    if remaining:
        return Step(
            "trial",
            snapshot=remaining[0],
            position=len(trials) + 1,
            total=total,
            surveys_done=n_surveys,
        )
    return Step("done", total=total, surveys_done=n_surveys)


def classify(correctness: str, decision: str) -> str:
    """How appropriate one decision was, for the H1 analysis."""
    follow = decision == RelianceDecisionEnum.FOLLOW
    if correctness == AdviceCorrectnessEnum.CORRECT:
        if follow:
            return "appropriate_reliance"
        if decision == RelianceDecisionEnum.ADJUST:
            return "adjusted_correct_advice"
        return "under_reliance"
    # incorrect, or not supported by the evidence
    return "over_reliance" if follow else "appropriate_self_reliance"


def scores(items: dict[str, int]) -> float:
    return round(sum(items.values()) / len(items), 2)
