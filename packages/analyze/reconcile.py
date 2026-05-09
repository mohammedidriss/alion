"""Reconcile live + offline detector outputs into consensus events.

Two detectors emit lists of punch events on the same session timeline.
This pairs them with a tolerance window and tags every output event
with which sources voted for it.

Three categories appear in the consensus stream:

- "consensus"  : both detectors fired within `tolerance_ms`, same hand.
- "live_only"  : only the live (heuristic) detector fired.
- "offline_only": only the offline (second-pass) detector fired.

Downstream consumers can choose to filter — e.g. RQ1 advice typically
uses `sources={"consensus"}` for max precision; the live counter uses
the union for max recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contracts import PunchEvent

ConsensusKind = Literal["consensus", "live_only", "offline_only"]


@dataclass(frozen=True)
class ConsensusEvent:
    t_ms: float
    hand: str
    velocity_ms: float
    punch_type: str | None
    confidence: float
    sources: tuple[str, ...]
    kind: ConsensusKind


def _key(e: PunchEvent) -> str:
    return e.hand


def reconcile_events(
    *,
    live: list[PunchEvent],
    offline: list[PunchEvent],
    tolerance_ms: float = 120.0,
    live_label: str = "live",
    offline_label: str = "offline",
) -> list[ConsensusEvent]:
    """Greedy nearest-match within tolerance, per hand.

    Algorithm:
    1. Index events by hand.
    2. For each live event, find the nearest unmatched offline event of
       the same hand within `tolerance_ms`. If found, emit a consensus
       event using the higher-confidence pick for velocity / type.
    3. Remaining live events → "live_only".
    4. Remaining offline events → "offline_only".
    """
    out: list[ConsensusEvent] = []
    # Index offline by hand for O(1)-ish neighbour search.
    offline_by_hand: dict[str, list[PunchEvent]] = {}
    for e in offline:
        offline_by_hand.setdefault(_key(e), []).append(e)
    for v in offline_by_hand.values():
        v.sort(key=lambda e: e.t_ms)
    matched_offline: set[int] = set()  # ids of matched offline events

    for le in sorted(live, key=lambda e: e.t_ms):
        candidates = offline_by_hand.get(_key(le), [])
        best_idx: int | None = None
        best_dt = float("inf")
        for idx, oe in enumerate(candidates):
            if id(oe) in matched_offline:
                continue
            dt = abs(oe.t_ms - le.t_ms)
            if dt < best_dt and dt <= tolerance_ms:
                best_dt = dt
                best_idx = idx
        if best_idx is not None:
            oe = candidates[best_idx]
            matched_offline.add(id(oe))
            # Take the higher-velocity reading; both detectors saw the
            # same physical event so the larger number is closer to truth.
            vel = max(le.velocity_ms, oe.velocity_ms)
            ptype = oe.punch_type or le.punch_type
            conf = max(le.confidence, oe.confidence)
            t_ms = (le.t_ms + oe.t_ms) / 2
            out.append(
                ConsensusEvent(
                    t_ms=t_ms,
                    hand=le.hand,
                    velocity_ms=vel,
                    punch_type=ptype,
                    confidence=min(1.0, conf + 0.1),  # small consensus bonus
                    sources=(live_label, offline_label),
                    kind="consensus",
                )
            )
        else:
            out.append(
                ConsensusEvent(
                    t_ms=le.t_ms,
                    hand=le.hand,
                    velocity_ms=le.velocity_ms,
                    punch_type=le.punch_type,
                    confidence=le.confidence,
                    sources=(live_label,),
                    kind="live_only",
                )
            )

    # Anything from offline that didn't get matched.
    for oe in offline:
        if id(oe) in matched_offline:
            continue
        out.append(
            ConsensusEvent(
                t_ms=oe.t_ms,
                hand=oe.hand,
                velocity_ms=oe.velocity_ms,
                punch_type=oe.punch_type,
                confidence=oe.confidence,
                sources=(offline_label,),
                kind="offline_only",
            )
        )

    out.sort(key=lambda e: e.t_ms)
    return out


__all__ = ["ConsensusEvent", "ConsensusKind", "reconcile_events"]
