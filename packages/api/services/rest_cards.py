"""Rest cards (ADR-041): what the corner sees in the minute between rounds.

From the RingsideIQ review board's blueprint. Two steps, both deterministic:

1. **The facts ledger** (`build_facts`): what the sensors say about the round just
   fought and the rest so far, each fact with an id, its numbers, the streams it
   came from and a quality from 0 to 1 (how much of the round those streams
   covered, how well the cameras and wrists agreed). A missing stream gives no
   fact, never a zero.
2. **Three cards** (`template_cards`), always in the same places: ▲ opportunity,
   ■ warning, ◆ recovery. Each is a fixed sentence built from the facts it cites.

A language model may then rephrase the cards (`coach.verify` checks every word
it writes against these facts, and any card that fails keeps its template). The
cards describe what happened; the coach decides what to say. Punches are
"thrown": nothing here can tell a landed punch from a blocked one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

Slot = Literal["opportunity", "warning", "recovery"]
SHAPES: dict[str, str] = {"opportunity": "▲", "warning": "■", "recovery": "◆"}
MIN_COVERAGE = 0.8  # a stream below this in the round says so on a card

_TYPE_NAMES = {
    ("lead", "straight"): "jab",
    ("rear", "straight"): "cross",
    ("lead", "hook"): "lead hook",
    ("rear", "hook"): "rear hook",
    ("lead", "uppercut"): "lead uppercut",
    ("rear", "uppercut"): "rear uppercut",
}


class Fact(BaseModel):
    id: str
    kind: str  # count, rate, change, hands, type, force, heart, rest, coverage
    round: int | None = None
    previous_round: int | None = None
    what: str  # machine name
    text: str  # how the fact reads
    value: float
    unit: str
    of: float | None = None
    previous: float | None = None
    direction: Literal["up", "down", "same"] | None = None
    hand: str | None = None  # lead / rear, or left / right without a stance
    streams: list[str]
    evidence: str = "thrown"  # the strongest the sensors support
    quality: float = Field(ge=0.0, le=1.0)


class Card(BaseModel):
    slot: Slot
    shape: str
    headline: str
    number: str | None = None
    context: str | None = None
    fact_ids: list[str]
    confidence: int = Field(ge=0, le=4)  # dots
    streams: list[str]
    source: Literal["template", "model"] = "template"


def facts_sha256(facts: list[Fact]) -> str:
    body = json.dumps([f.model_dump() for f in facts], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _num(x: float) -> str:
    """How a number is written everywhere: whole when it is whole, else one decimal."""
    r = round(x, 1)
    return str(int(r)) if r == int(r) else f"{r:.1f}"


def _pct_change(now: float, before: float) -> int:
    return round((now - before) / before * 100)


def _side(hand: str, stance: str | None) -> str:
    if stance == "orthodox":
        return "lead" if hand == "left" else "rear"
    if stance == "southpaw":
        return "lead" if hand == "right" else "rear"
    return hand


def _punches(rnd: Any, source: str) -> tuple[int, float | None, int, int, list[str], float] | None:
    """(count, per minute, left, right, streams, quality) for a round, or None."""
    xc = rnd.cross_check
    cov = rnd.coverage or {}
    wrist_cov = [v for k, v in cov.items() if k.startswith("wrist_") and v is not None]
    if xc is not None:
        q = xc.agreement if xc.agreement is not None else 0.8
        return (
            xc.punch_count,
            xc.ppm,
            xc.left,
            xc.right,
            ["wrists", "cameras"],
            max(0.3, min(1.0, q + 0.1)),
        )
    if source == "wrist" or (rnd.imu and rnd.imu.punch_count):
        q = min(wrist_cov) if wrist_cov else 0.8
        return rnd.imu.punch_count, rnd.imu.ppm, rnd.imu.left, rnd.imu.right, ["wrists"], q
    if source == "camera" and rnd.cv is not None:
        left = sum(1 for e in rnd.cv.events if e.hand == "left")
        return rnd.cv.punch_count, rnd.cv.ppm, left, rnd.cv.punch_count - left, ["cameras"], 0.7
    return None


def build_facts(ex: Any, after_round: int, live_rest: dict[str, float] | None = None) -> list[Fact]:
    """The ledger after `after_round` (1-based) from a rounds export. `live_rest`
    ({"elapsed_s", "hr_now"}) adds recovery so far while the rest is running."""
    rounds = ex.rounds
    if not 1 <= after_round <= len(rounds):
        return []
    k = after_round
    r = rounds[k - 1]
    prev = rounds[k - 2] if k >= 2 else None
    stance = ex.stance
    facts: list[Fact] = []

    def add(**kw: Any) -> Fact:
        f = Fact(id=f"F{len(facts) + 1}", **kw)
        facts.append(f)
        return f

    cur = _punches(r, ex.punch_source)
    if cur is not None and cur[0] > 0:
        count, ppm, left, right, streams, q = cur
        add(
            kind="count",
            round=k,
            what="punches",
            text=f"{count} punches in round {k}",
            value=count,
            unit="punches",
            streams=streams,
            quality=round(q, 2),
        )
        before = _punches(prev, ex.punch_source) if prev is not None else None
        if before is not None and before[1] and ppm:
            pct = _pct_change(ppm, before[1])
            add(
                kind="change",
                round=k,
                previous_round=k - 1,
                what="output_vs_previous",
                text=f"punches per minute {_num(ppm)} against {_num(before[1])} in round {k - 1}",
                value=abs(pct),
                unit="%",
                previous=round(before[1], 1),
                direction="up" if pct > 0 else "down" if pct < 0 else "same",
                streams=streams,
                quality=round(min(q, before[5]), 2),
            )
        first = _punches(rounds[0], ex.punch_source) if k >= 3 else None
        if first is not None and first[1] and ppm:
            pct = _pct_change(ppm, first[1])
            add(
                kind="change",
                round=k,
                previous_round=1,
                what="output_vs_first",
                text=f"punches per minute {_num(ppm)} against {_num(first[1])} in round 1",
                value=abs(pct),
                unit="%",
                previous=round(first[1], 1),
                direction="up" if pct > 0 else "down" if pct < 0 else "same",
                streams=streams,
                quality=round(min(q, first[5]), 2),
            )
        if left + right > 0:
            for hand, n in (("left", left), ("right", right)):
                side = _side(hand, stance)
                add(
                    kind="hands",
                    round=k,
                    what=f"{side}_hand",
                    hand=side,
                    text=f"{side} hand threw {n} of {left + right}",
                    value=n,
                    of=left + right,
                    unit="punches",
                    streams=streams,
                    quality=round(q, 2),
                )

    # Punch types, when a type model named them (after the session: cameras or wrists).
    xc = r.cross_check
    if xc is not None and xc.types:
        prev_types = prev.cross_check.types if prev is not None and prev.cross_check else None
        total = sum(v.get("total", 0) for v in xc.types.values())
        for hand, tally in xc.types.items():
            side = _side(hand, stance)
            for motion in ("straight", "hook", "uppercut"):
                name = _TYPE_NAMES.get((side, motion), f"{hand} {motion}")
                n = tally.get(motion, 0)
                before_n = (prev_types or {}).get(hand, {}).get(motion) if prev_types else None
                if n == 0 and not before_n:
                    continue
                add(
                    kind="type",
                    round=k,
                    previous_round=k - 1 if before_n is not None else None,
                    what=name.replace(" ", "_"),
                    hand=side,
                    text=f"{name}: {n} of {total}",
                    value=n,
                    of=total,
                    previous=before_n,
                    unit="punches",
                    direction=None
                    if before_n is None
                    else "up"
                    if n > before_n
                    else "down"
                    if n < before_n
                    else "same",
                    streams=["wrists", "cameras"],
                    quality=0.8,
                )

    # Wrist force, when the wrists felt the punches; a clipped reading is a minimum.
    if r.imu.mean_peak_g is not None:
        clipped = r.imu.clipped
        add(
            kind="force",
            round=k,
            what="mean_peak_g",
            text=f"mean wrist peak {_num(r.imu.mean_peak_g)} g"
            + (" (at least: readings clipped)" if clipped else ""),
            value=round(r.imu.mean_peak_g, 1),
            unit="g",
            previous=round(prev.imu.mean_peak_g, 1)
            if prev is not None and prev.imu.mean_peak_g
            else None,
            previous_round=k - 1 if prev is not None and prev.imu.mean_peak_g else None,
            streams=["wrists"],
            quality=0.4 if clipped else 0.8,
        )

    # Heart rate in the round, against the round before.
    h = r.hrv
    if h.mean_hr_bpm is not None:
        cov_h = (r.coverage or {}).get("heart")
        q = cov_h if cov_h is not None else 0.8
        ph = prev.hrv.mean_hr_bpm if prev is not None else None
        add(
            kind="heart",
            round=k,
            previous_round=k - 1 if ph is not None else None,
            what="mean_hr",
            text=f"average heart rate {_num(h.mean_hr_bpm)} in round {k}",
            value=round(h.mean_hr_bpm),
            unit="bpm",
            previous=round(ph) if ph is not None else None,
            direction=None
            if ph is None
            else "up"
            if h.mean_hr_bpm > ph
            else "down"
            if h.mean_hr_bpm < ph
            else "same",
            streams=["heart"],
            quality=round(q, 2),
        )
        if h.peak_hr_bpm is not None:
            add(
                kind="heart",
                round=k,
                what="peak_hr",
                text=f"peak heart rate {_num(h.peak_hr_bpm)} in round {k}",
                value=round(h.peak_hr_bpm),
                unit="bpm",
                streams=["heart"],
                quality=round(q, 2),
            )

    # Recovery in this rest: so far (live), or at 60 s / 30 s (after the session).
    rest = r.rest
    prev_rest = prev.rest if prev is not None else None
    if live_rest and rest is not None and rest.hr_at_bell is not None and live_rest.get("hr_now"):
        drop = rest.hr_at_bell - live_rest["hr_now"]
        add(
            kind="rest",
            round=k,
            what="hr_drop_so_far",
            text=f"heart rate down {_num(drop)} in {_num(live_rest['elapsed_s'])} s of rest",
            value=round(drop),
            unit="bpm",
            of=round(live_rest["elapsed_s"]),
            direction="down",
            streams=["heart"],
            quality=0.85,
        )
    elif rest is not None and (rest.drop_60s is not None or rest.drop_30s is not None):
        secs = 60 if rest.drop_60s is not None else 30
        drop = rest.drop_60s if rest.drop_60s is not None else rest.drop_30s
        assert drop is not None
        before = None
        if prev_rest is not None:
            before = prev_rest.drop_60s if secs == 60 else prev_rest.drop_30s
        add(
            kind="rest",
            round=k,
            previous_round=k - 1 if before is not None else None,
            what=f"hr_drop_{secs}s",
            text=f"heart rate down {_num(drop)} in {secs} s of rest",
            value=round(drop),
            unit="bpm",
            of=secs,
            previous=round(before) if before is not None else None,
            direction="down",
            streams=["heart"],
            quality=0.9,
        )
        if before is not None:
            add(
                kind="rest",
                round=k,
                previous_round=k - 1,
                what="recovery_vs_previous",
                text=f"recovery {_num(drop)} against {_num(before)} after round {k - 1}",
                value=round(drop),
                previous=round(before),
                of=secs,
                unit="bpm",
                direction="up" if drop > before else "down" if drop < before else "same",
                streams=["heart"],
                quality=0.9,
            )

    # A stream that missed part of the round says so.
    for stream, share in sorted((r.coverage or {}).items()):
        if share is not None and share < MIN_COVERAGE:
            add(
                kind="coverage",
                round=k,
                what=f"coverage_{stream}",
                text=f"{stream.replace('_', ' ')} data for {round(share * 100)}% of round {k}",
                value=round(share * 100),
                unit="%",
                streams=[stream.split("_")[0] + "s" if stream.startswith("wrist") else stream],
                quality=1.0,
            )
    return facts


def _dots(facts: list[Fact]) -> int:
    q = min((f.quality for f in facts), default=0.0)
    return 4 if q >= 0.9 else 3 if q >= 0.75 else 2 if q >= 0.5 else 1


def _card(
    slot: Slot, headline: str, number: str | None, context: str | None, cited: list[Fact]
) -> Card:
    streams = sorted({s for f in cited for s in f.streams})
    return Card(
        slot=slot,
        shape=SHAPES[slot],
        headline=headline,
        number=number,
        context=context,
        fact_ids=[f.id for f in cited],
        confidence=_dots(cited) if cited else 0,
        streams=streams,
    )


def _empty(slot: Slot, text: str) -> Card:
    return Card(slot=slot, shape=SHAPES[slot], headline=text, fact_ids=[], confidence=0, streams=[])


def template_cards(facts: list[Fact]) -> list[Card]:
    """Three cards from the ledger, by fixed rules; a slot with nothing to say
    says so, so the layout never moves."""
    by = {f.what: f for f in facts}
    k = next((f.round for f in facts if f.round is not None), None)
    out: list[Card] = []

    # ▲ opportunity
    up = by.get("output_vs_previous")
    types = sorted((f for f in facts if f.kind == "type" and f.of), key=lambda f: -f.value)
    hands = [f for f in facts if f.kind == "hands"]
    if up is not None and up.direction == "up" and up.value >= 10:
        out.append(
            _card(
                "opportunity",
                f"Output up {_num(up.value)}% on round {up.previous_round}",
                f"+{_num(up.value)}%",
                f"punches per minute, round {k}",
                [up],
            )
        )
    elif types and types[0].of and types[0].value / types[0].of >= 0.35:
        t = types[0]
        name = t.what.replace("_", " ")
        out.append(
            _card(
                "opportunity",
                f"{name.capitalize()} most used",
                f"{_num(t.value)} of {_num(t.of or 0)}",
                f"punches in round {k}",
                [t],
            )
        )
    elif len(hands) == 2 and all(h.of and h.value / h.of >= 0.4 for h in hands):
        a, b = hands
        out.append(
            _card(
                "opportunity",
                "Both hands busy",
                f"{_num(a.value)}–{_num(b.value)}",
                f"{a.hand} and {b.hand}, round {k}",
                hands,
            )
        )
    elif "punches" in by:
        f = by["punches"]
        out.append(
            _card(
                "opportunity",
                f"{_num(f.value)} punches in round {k}",
                _num(f.value),
                "thrown, all hands",
                [f],
            )
        )
    else:
        out.append(_empty("opportunity", "No punch data this round"))

    # ■ warning
    cover = [f for f in facts if f.kind == "coverage" and f.value < 60]
    down = by.get("output_vs_previous")
    weak = [h for h in hands if h.of and h.value / h.of < 0.3]
    dropped = [f for f in facts if f.kind == "type" and f.value == 0 and (f.previous or 0) > 0]
    fade = by.get("output_vs_first")
    if cover:
        f = cover[0]
        out.append(
            _card(
                "warning",
                f"{f.what.removeprefix('coverage_').replace('_', ' ').capitalize()} data missing",
                f"{_num(f.value)}%",
                f"of round {k} recorded",
                [f],
            )
        )
    elif down is not None and down.direction == "down" and down.value >= 10:
        out.append(
            _card(
                "warning",
                f"Output down {_num(down.value)}% on round {down.previous_round}",
                f"−{_num(down.value)}%",
                f"punches per minute, round {k}",
                [down],
            )
        )
    elif weak:
        h = weak[0]
        out.append(
            _card(
                "warning",
                f"{(h.hand or '').capitalize()} hand quiet",
                f"{_num(h.value)} of {_num(h.of or 0)}",
                f"punches in round {k}",
                [h],
            )
        )
    elif dropped:
        f = dropped[0]
        name = f.what.replace("_", " ")
        out.append(
            _card(
                "warning",
                f"No {name}s this round",
                "0",
                f"{_num(f.previous or 0)} in round {f.previous_round}",
                [f],
            )
        )
    elif fade is not None and fade.direction == "down" and fade.value >= 15:
        out.append(
            _card(
                "warning",
                f"Output down {_num(fade.value)}% on round 1",
                f"−{_num(fade.value)}%",
                f"punches per minute, round {k}",
                [fade],
            )
        )
    else:
        out.append(_empty("warning", "Nothing new this round"))

    # ◆ recovery
    rest = next((f for f in facts if f.kind == "rest" and f.what.startswith("hr_drop")), None)
    vs = by.get("recovery_vs_previous")
    hr = by.get("mean_hr")
    if rest is not None:
        ctx = None
        cited = [rest]
        if vs is not None and vs.direction in ("up", "down"):
            ctx = f"{'faster' if vs.direction == 'up' else 'slower'} than round {vs.previous_round} ({_num(vs.previous or 0)})"
            cited.append(vs)
        out.append(
            _card(
                "recovery",
                f"Heart rate down {_num(rest.value)} in {_num(rest.of or 0)} s",
                f"−{_num(rest.value)} bpm",
                ctx,
                cited,
            )
        )
    elif hr is not None:
        ctx = (
            f"{'up' if hr.direction == 'up' else 'down'} on round {hr.previous_round} ({_num(hr.previous or 0)})"
            if hr.direction in ("up", "down")
            else f"round {k}"
        )
        out.append(
            _card(
                "recovery",
                f"Average heart rate {_num(hr.value)}",
                f"{_num(hr.value)} bpm",
                ctx,
                [hr],
            )
        )
    else:
        out.append(_empty("recovery", "No heart data"))
    return out
