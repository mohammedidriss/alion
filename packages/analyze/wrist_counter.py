"""Punches from the wrists without knowing the punch type (ADR-060).

The detector's defaults (`imu_punches`) suit straights: a hook's gentler burst
falls under its threshold, and an uppercut's return to guard is counted as a
second punch. Inside a typed protocol block the labeler knows the type and uses
its profile; in a round nobody does. So:

1. **Candidates**: every burst a sensitive setting finds (0.8 g, 200 ms apart),
   which catches the hooks along with every return and shake.
2. **Keep or drop**: a trained classifier decides each candidate from the burst's
   shape (`wrist_types.features`, the punch-type model's window) and its context —
   how tall it is, how far and how tall the bursts before and after it on the same
   wrist are, and how much the other wrist moved at the same time.
3. **One per 300 ms**: of two kept punches on one wrist closer than that, the
   likelier stays.

Pure numpy; the classifier is any object with `predict_proba` (services.wrist_counter
trains it on the labelled takes).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from analyze import wrist_types as wt
from analyze.imu_punches import ImuPunch, detect_punches

CANDIDATE: dict[str, Any] = {"threshold_g": 0.8, "min_gap_ms": 200.0}
GAP_MS = 300.0  # two punches on one wrist are at least this far apart
MATCH_MS = 150.0  # a candidate is a labelled punch within this
OTHER_MS = 300.0  # the other wrist's movement around a candidate
CAP_MS = 3000.0  # a neighbour farther than this is "none"

CONTEXT = 8  # the context features after the window's
N_FEATURES = len(wt.features(np.zeros((len(wt.GRID), 6)), "left")) + CONTEXT

Stream = tuple[np.ndarray, np.ndarray]  # t_ms (sorted), (n, 6): ax, ay, az, gx, gy, gz


def candidates(t: np.ndarray, imu: np.ndarray) -> list[ImuPunch]:
    if len(t) < 20:
        return []
    return detect_punches(t, imu[:, 0], imu[:, 1], imu[:, 2], **CANDIDATE)


def _moved(other: Stream | None, at_ms: float) -> float:
    """The other wrist's largest dynamic acceleration within OTHER_MS of `at_ms`."""
    if other is None or len(other[0]) == 0:
        return 0.0
    t, imu = other
    i0 = int(np.searchsorted(t, at_ms - OTHER_MS))
    i1 = int(np.searchsorted(t, at_ms + OTHER_MS, side="right"))
    if i1 <= i0:
        return 0.0
    return float(np.max(np.abs(np.linalg.norm(imu[i0:i1, :3], axis=1) - 1.0)))


def rows(
    stream: Stream, hand: str, cands: list[ImuPunch], other: Stream | None
) -> tuple[np.ndarray, list[int]]:
    """One feature row per candidate with a usable window, and which candidates."""
    t, imu = stream
    out: list[np.ndarray] = []
    idx: list[int] = []
    for k, c in enumerate(cands):
        win = wt.window(t, imu, c.t_ms)
        if win is None:
            continue
        prev = cands[k - 1] if k else None
        nxt = cands[k + 1] if k + 1 < len(cands) else None
        prev_g = prev.peak_g if prev else 0.0
        next_g = nxt.peak_g if nxt else 0.0
        context = [
            c.peak_g,
            min(c.t_ms - prev.t_ms, CAP_MS) if prev else CAP_MS,
            min(nxt.t_ms - c.t_ms, CAP_MS) if nxt else CAP_MS,
            prev_g,
            next_g,
            _moved(other, c.t_ms),
            c.peak_g / max(prev_g, 0.1),
            c.peak_g / max(next_g, 0.1),
        ]
        out.append(np.concatenate([wt.features(win, hand), context]))
        idx.append(k)
    return (np.array(out) if out else np.zeros((0, N_FEATURES))), idx


def keep(cands: list[ImuPunch], probs: dict[int, float], threshold: float) -> list[ImuPunch]:
    """The candidates the classifier kept, one per GAP_MS on the wrist, oldest first."""
    kept: list[int] = []
    for k in sorted((k for k, p in probs.items() if p >= threshold), key=lambda k: -probs[k]):
        if all(abs(cands[k].t_ms - cands[j].t_ms) >= GAP_MS for j in kept):
            kept.append(k)
    return [cands[k] for k in sorted(kept)]


def find(model: Any, threshold: float, streams: dict[str, Stream]) -> dict[str, list[ImuPunch]]:
    """Each wrist's punches, by the trained classifier."""
    out: dict[str, list[ImuPunch]] = {}
    for hand, stream in streams.items():
        other = streams.get("right" if hand == "left" else "left")
        cands = candidates(*stream)
        x, idx = rows(stream, hand, cands, other)
        probs: dict[int, float] = {}
        if len(idx):
            p = model.predict_proba(x)[:, list(model.classes_).index(1)]
            probs = {k: float(v) for k, v in zip(idx, p, strict=True)}
        out[hand] = keep(cands, probs, threshold)
    return out


def matched(found_ms: list[float], truth_ms: list[float], ms: float = MATCH_MS) -> set[int]:
    """Which of `found_ms` are labelled punches: each label takes its nearest
    unclaimed find within `ms`."""
    used: set[int] = set()
    for lt in truth_ms:
        best = None
        for k, f in enumerate(found_ms):
            if k in used or abs(f - lt) > ms:
                continue
            if best is None or abs(f - lt) < abs(found_ms[best] - lt):
                best = k
        if best is not None:
            used.add(best)
    return used
