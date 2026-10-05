"""Cross-check punches between the wrist sensors and the cameras.

The two kinds of sensor fail differently, so each one checks the other:

* The wrist IMUs feel *when* a hand accelerates — precisely, and whether or not a
  camera can see it — and how hard (g). They can't see which arm they're
  strapped to, and they stop at a Bluetooth dropout.
* The cameras see *which* hand moved and how fast it travelled. Browser pose
  jitters (one camera alone over-counts 1.1–2× against the wrists) and an arm
  can be hidden from a camera.

How a session's punches are settled:

1. Each camera's pose is smoothed (`smooth_pose`: 30 Hz, 100 ms window) and run
   through the heuristic detector with a 350 ms refractory — the browser-camera
   profile (`camera_punches`). Raw browser pose reads ~3× too many punches.
2. Each camera's clock is checked against the wrists (`sync_offset`) and its
   offset removed.
3. Cameras vote (`vote`): a camera punch is one at least two cameras saw within
   120 ms of each other (with one camera, its own punches).
4. Left/right are checked (`hands_verdict`) on isolated punches. If the cameras
   mostly name the other hand, the sensors are on the wrong wrists and the
   wrist hands are swapped.
5. Camera votes are paired one-to-one with wrist punches within ±150 ms
   (`cross_check`), closest first:
   * both → **confirmed**: wrist time, hand and impact (g), camera speed;
   * wrist only → counted (the wrists are the validated counter; the cameras
     may not have seen that arm);
   * camera only → counted only where that wrist's sensor wasn't streaming (a
     dropout, or not worn); otherwise reported but not counted, since most
     are pose jitter.

Validated 2026-10-05 against two recordings (3 cameras + both wrists): the
camera vote agreed with the wrists on 90% / 79% of wrist punches, and step 4
flagged the RQ2 take whose sensors were on the wrong wrists (196 vs 49) while
the free-training session came out "unclear".

Speed is the camera's peak wrist-landmark speed — a relative index for
comparing punches and sessions, not the glove's true speed.
"""

from __future__ import annotations

import bisect
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

import numpy as np

from analyze.punch_detector_heuristic import HeuristicPunchDetector
from contracts import Hand, Landmark, PoseFrame, PunchEvent, WorldLandmark

Source = Literal["both", "wrist", "camera"]
HandsVerdict = Literal["consistent", "swapped", "unclear"]

# Browser-camera profile.
SMOOTH_HZ = 30.0
SMOOTH_WIN_MS = 100.0
CAMERA_REFRACTORY_MS = 350.0

VOTE_TOL_MS = 120.0  # cameras agree on one punch
MATCH_TOL_MS = 150.0  # a camera punch and a wrist punch are the same punch
HAND_MISMATCH_COST_MS = 100.0  # pairing penalty when trusted hands disagree
SYNC_MIN_PAIRS = 20
SYNC_SEARCH_MS = 400.0
HANDS_ISOLATION_MS = 350.0  # only one wrist punch this close → unambiguous hand
HANDS_MIN_PUNCHES = 30
HANDS_RATIO = 2.0
GAP_MS = 500.0  # a wrist stream silent this long wasn't recording


@dataclass(frozen=True)
class WristPunch:
    t_ms: float
    hand: Hand
    peak_g: float


@dataclass(frozen=True)
class CameraPunch:
    t_ms: float
    hand: Hand
    speed_ms: float
    cameras: tuple[str, ...]


@dataclass(frozen=True)
class FusedPunch:
    t_ms: float
    hand: Hand
    source: Source
    counted: bool
    peak_g: float | None = None
    speed_ms: float | None = None
    cameras: tuple[str, ...] = ()


@dataclass(frozen=True)
class CameraReport:
    device: str
    punches: int
    offset_ms: float | None  # clock correction applied (None: too few pairs to tell)
    agreement: float | None  # share of its punches the wrists confirm
    coverage: float | None  # share of the wrist punches it saw
    hands: HandsVerdict


@dataclass(frozen=True)
class CrossCheck:
    punches: list[FusedPunch]  # everything either side saw, counted or not
    cameras: list[CameraReport]
    hands: HandsVerdict
    hands_swapped: bool  # the wrist hands were corrected from the cameras
    wrist_punches: int
    camera_punches: int  # after the vote

    @property
    def counted(self) -> list[FusedPunch]:
        return [p for p in self.punches if p.counted]


# --------------------------------------------------------------------------
# Camera side
# --------------------------------------------------------------------------


def smooth_pose(
    frames: Sequence[PoseFrame], *, hz: float = SMOOTH_HZ, win_ms: float = SMOOTH_WIN_MS
) -> list[PoseFrame]:
    """Every landmark averaged over a `win_ms` window, sampled at a fixed `hz`.

    Browser pose arrives at an uneven 24–60 fps with frame-to-frame jitter that
    reads as 1–3 m/s of wrist speed while standing still; averaging over 100 ms
    removes it and puts every camera on the same frame rate."""
    if len(frames) < 2:
        return list(frames)
    frames = sorted(frames, key=lambda f: f.t_ms)
    t = np.array([f.t_ms for f in frames], dtype=float)
    lm = np.array([[(p.x, p.y, p.z, p.visibility) for p in f.landmarks] for f in frames])
    has_w = np.array([f.world_landmarks is not None for f in frames], dtype=float)
    wl = np.zeros_like(lm)
    for i, f in enumerate(frames):
        if f.world_landmarks is not None:
            wl[i] = [(p.x, p.y, p.z, p.visibility) for p in f.world_landmarks]

    def csum(a: np.ndarray) -> np.ndarray:
        return np.concatenate((np.zeros((1, *a.shape[1:])), np.cumsum(a, axis=0)))

    cs_l, cs_w, cs_n = csum(lm), csum(wl), csum(has_w)
    grid = np.arange(t[0], t[-1] + 1e-9, 1000.0 / hz)
    lo = np.searchsorted(t, grid - win_ms / 2, side="left")
    hi = np.searchsorted(t, grid + win_ms / 2, side="right")
    sid = frames[0].session_id
    out: list[PoseFrame] = []
    for k in range(len(grid)):
        a, b = int(lo[k]), int(hi[k])
        if b <= a:
            continue  # no frame in this window (a dropout) — leave the gap
        mean_l = (cs_l[b] - cs_l[a]) / (b - a)
        n_w = cs_n[b] - cs_n[a]
        world = None
        if n_w > 0:
            mean_w = (cs_w[b] - cs_w[a]) / n_w
            world = tuple(
                WorldLandmark.model_construct(x=x, y=y, z=z, visibility=min(1.0, max(0.0, v)))
                for x, y, z, v in mean_w.tolist()
            )
        out.append(
            PoseFrame.model_construct(
                session_id=sid,
                frame_index=len(out),
                t_ms=float(grid[k]),
                landmarks=tuple(
                    Landmark.model_construct(x=x, y=y, z=z, visibility=min(1.0, max(0.0, v)))
                    for x, y, z, v in mean_l.tolist()
                ),
                world_landmarks=world,
            )
        )
    return out


def camera_punches(frames: Sequence[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
    """One browser camera's punches: smoothed pose through the heuristic detector."""
    det = HeuristicPunchDetector(stance=stance, refractory_ms=CAMERA_REFRACTORY_MS)
    out: list[PunchEvent] = []
    for f in smooth_pose(frames):
        out.extend(det.feed(f))
    return out


def vote(
    per_camera: Mapping[str, Sequence[PunchEvent]],
    *,
    offsets: Mapping[str, float] | None = None,
    tol_ms: float = VOTE_TOL_MS,
    min_cameras: int | None = None,
) -> list[CameraPunch]:
    """Punches enough cameras agree on: groups of detections from different
    cameras within `tol_ms`, kept when ≥ `min_cameras` cameras are in the group
    (default 2, or 1 when there's only one camera)."""
    need = min_cameras if min_cameras is not None else (2 if len(per_camera) > 1 else 1)
    offsets = offsets or {}
    allev = sorted(
        (e.t_ms - offsets.get(dev, 0.0), e.hand, e.velocity_ms, dev)
        for dev, evs in per_camera.items()
        for e in evs
    )
    out: list[CameraPunch] = []
    i = 0
    while i < len(allev):
        j = i
        while j + 1 < len(allev) and allev[j + 1][0] - allev[i][0] <= tol_ms:
            j += 1
        grp = allev[i : j + 1]
        cams = tuple(sorted({g[3] for g in grp}))
        if len(cams) >= need:
            hands = Counter(g[1] for g in grp).most_common()
            # A tie goes to the hand of the fastest detection.
            hand = (
                hands[0][0]
                if len(hands) == 1 or hands[0][1] > hands[1][1]
                else max(grp, key=lambda g: g[2])[1]
            )
            # Per camera its fastest detection, then the median across cameras.
            speeds = [max(g[2] for g in grp if g[3] == c) for c in cams]
            out.append(
                CameraPunch(
                    t_ms=float(np.median([g[0] for g in grp])),
                    hand=hand,
                    speed_ms=round(float(np.median(speeds)), 2),
                    cameras=cams,
                )
            )
        i = j + 1
    return out


# --------------------------------------------------------------------------
# Wrist ↔ camera
# --------------------------------------------------------------------------


def sync_offset(camera_t: Sequence[float], wrist_t: Sequence[float]) -> float | None:
    """How far a camera's punches sit after the wrists' (ms), or None when too
    few punches pair up to tell."""
    wt = sorted(wrist_t)
    if not wt:
        return None
    dts: list[float] = []
    for t in camera_t:
        i = bisect.bisect_left(wt, t)
        near = [wt[k] for k in (i - 1, i) if 0 <= k < len(wt)]
        d = min((t - w for w in near), key=abs)
        if abs(d) <= SYNC_SEARCH_MS:
            dts.append(d)
    if len(dts) < SYNC_MIN_PAIRS:
        return None
    # Two passes: the median of everything, then of what sits close to it.
    m = float(np.median(dts))
    close = [d for d in dts if abs(d - m) <= MATCH_TOL_MS]
    return round(float(np.median(close)), 1) if len(close) >= SYNC_MIN_PAIRS else None


def hands_verdict(
    camera: Sequence[tuple[float, Hand]], wrist: Sequence[WristPunch]
) -> tuple[HandsVerdict, int, int]:
    """Do the cameras and the wrists name the same hand? (verdict, same, opposite)

    Only isolated punches count — one wrist punch within 350 ms — since in a fast
    combination both hands move inside the matching window."""
    wt = [w.t_ms for w in wrist]
    same = opposite = 0
    for t, hand in camera:
        lo = bisect.bisect_left(wt, t - HANDS_ISOLATION_MS)
        hi = bisect.bisect_right(wt, t + HANDS_ISOLATION_MS)
        if hi - lo != 1 or abs(wt[lo] - t) > MATCH_TOL_MS:
            continue
        if wrist[lo].hand == hand:
            same += 1
        else:
            opposite += 1
    if same + opposite >= HANDS_MIN_PUNCHES:
        if opposite >= HANDS_RATIO * max(same, 1):
            return "swapped", same, opposite
        if same >= HANDS_RATIO * max(opposite, 1):
            return "consistent", same, opposite
    return "unclear", same, opposite


def _pair(
    a_t: Sequence[float],
    a_hand: Sequence[Hand],
    b_t: Sequence[float],
    b_hand: Sequence[Hand],
    *,
    hands_trusted: bool,
) -> dict[int, int]:
    """One-to-one pairs a → b within ±MATCH_TOL_MS, closest first."""
    order = sorted(range(len(b_t)), key=lambda k: b_t[k])
    bt = [b_t[k] for k in order]
    cand: list[tuple[float, int, int]] = []
    for i, t in enumerate(a_t):
        k = bisect.bisect_left(bt, t - MATCH_TOL_MS)
        while k < len(bt) and bt[k] <= t + MATCH_TOL_MS:
            j = order[k]
            cost = abs(bt[k] - t)
            if hands_trusted and a_hand[i] != b_hand[j]:
                cost += HAND_MISMATCH_COST_MS
            cand.append((cost, i, j))
            k += 1
    pairs: dict[int, int] = {}
    used_b: set[int] = set()
    for _, i, j in sorted(cand):
        if i not in pairs and j not in used_b:
            pairs[i] = j
            used_b.add(j)
    return pairs


def _in_gap(t: float, gaps: Sequence[tuple[float, float]]) -> bool:
    return any(a <= t <= b for a, b in gaps)


def wrist_gaps(
    t_by_hand: Mapping[Hand, Sequence[float]], start_ms: float, end_ms: float
) -> dict[Hand, list[tuple[float, float]]]:
    """Stretches of [start, end] where each wrist's sensor wasn't streaming."""
    out: dict[Hand, list[tuple[float, float]]] = {}
    for hand in ("left", "right"):
        ts = sorted(t_by_hand.get(hand, ()))
        edges = [start_ms - GAP_MS, *ts, end_ms + GAP_MS]
        out[hand] = [
            (max(start_ms, a), min(end_ms, b)) for a, b in pairwise(edges) if b - a > GAP_MS
        ]
    return out


def _flip(hand: Hand) -> Hand:
    return "right" if hand == "left" else "left"


def cross_check(
    wrist: Sequence[WristPunch],
    per_camera: Mapping[str, Sequence[PunchEvent]],
    *,
    gaps: Mapping[Hand, Sequence[tuple[float, float]]] | None = None,
) -> CrossCheck:
    """Settle a recording's punches from both sides (see the module docstring).

    `gaps` are the stretches each wrist sensor wasn't streaming (`wrist_gaps`);
    camera-only punches there are counted. None means the wrists streamed
    throughout — or, with no wrist punches at all, that there were no wrist
    sensors, and the cameras' vote is the count."""
    wrist = sorted(wrist, key=lambda w: w.t_ms)
    if gaps is None:
        gaps = {} if wrist else {"left": [(-np.inf, np.inf)], "right": [(-np.inf, np.inf)]}
    wt = [w.t_ms for w in wrist]

    offsets: dict[str, float] = {}
    for dev, evs in per_camera.items():
        off = sync_offset([e.t_ms for e in evs], wt)
        if off is not None:
            offsets[dev] = off
    votes = vote(per_camera, offsets=offsets)

    hands, _, _ = hands_verdict([(v.t_ms, v.hand) for v in votes], wrist)
    swapped = hands == "swapped"
    sensors = wrist  # as the sensors labelled them
    if swapped:
        # The sensor labelled "left" was on the right wrist: its punches and its
        # dropouts belong to the right hand.
        wrist = [WristPunch(w.t_ms, _flip(w.hand), w.peak_g) for w in wrist]
        gaps = {"left": gaps.get("right", ()), "right": gaps.get("left", ())}

    pairs = _pair(
        [v.t_ms for v in votes],
        [v.hand for v in votes],
        wt,
        [w.hand for w in wrist],
        hands_trusted=hands != "unclear",
    )
    out: list[FusedPunch] = []
    for i, v in enumerate(votes):
        if i in pairs:
            w = wrist[pairs[i]]
            out.append(FusedPunch(w.t_ms, w.hand, "both", True, w.peak_g, v.speed_ms, v.cameras))
        else:
            # Unclear hands: a dropout on either wrist could have hidden it.
            check: list[Hand] = [v.hand] if hands != "unclear" else ["left", "right"]
            dropout = any(_in_gap(v.t_ms, gaps.get(h, ())) for h in check)
            out.append(FusedPunch(v.t_ms, v.hand, "camera", dropout, None, v.speed_ms, v.cameras))
    paired = set(pairs.values())
    out += [
        FusedPunch(w.t_ms, w.hand, "wrist", True, w.peak_g)
        for j, w in enumerate(wrist)
        if j not in paired
    ]

    reports: list[CameraReport] = []
    for dev, evs in sorted(per_camera.items()):
        ct = [e.t_ms - offsets.get(dev, 0.0) for e in evs]
        ch: list[Hand] = [e.hand for e in evs]
        if wrist:
            # Hand-agnostic pairing: this is about whether the camera saw the
            # punch at all; its hands get their own verdict.
            n = len(_pair(ct, ch, wt, [w.hand for w in wrist], hands_trusted=False))
            cam_hands, _, _ = hands_verdict(list(zip(ct, ch, strict=True)), sensors)
        else:
            n, cam_hands = 0, "unclear"
        reports.append(
            CameraReport(
                device=dev,
                punches=len(evs),
                offset_ms=offsets.get(dev),
                agreement=round(n / len(evs), 2) if wrist and evs else None,
                coverage=round(n / len(wrist), 2) if wrist else None,
                hands=cam_hands,
            )
        )
    return CrossCheck(
        punches=sorted(out, key=lambda p: p.t_ms),
        cameras=reports,
        hands=hands,
        hands_swapped=swapped,
        wrist_punches=len(wrist),
        camera_punches=len(votes),
    )
