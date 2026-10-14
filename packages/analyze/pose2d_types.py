"""Punch motion from 2D pose alone — straight, hook or uppercut — so a model can
learn from 2D datasets (BoxingVI: COCO-17 keypoints from YouTube video) and be
tested on this project's cameras (MediaPipe's 33 landmarks, read in 2D).

A clip is one punch: frames of COCO-17 (x, y) in image coordinates. `features`
normalises it (origin at the first frame's mid-shoulder, scale the clip's
shoulder width or, side-on, its torso), picks the arm that moved most (the
punching arm, so the model doesn't need the hand or the stance), resamples to a
fixed number of frames and returns one row: the punching arm's wrist and elbow
over time relative to its shoulder, its elbow angle, the wrist's speed, the other
wrist, and summary shape numbers. Research — on the research/boxingvi-camera-types
branch.
"""

from __future__ import annotations

import numpy as np

MOTIONS = ("straight", "hook", "uppercut")
BOXINGVI_CLASS = {
    "jab": "straight",
    "cross": "straight",
    "lead hook": "hook",
    "rear hook": "hook",
    "lead uppercut": "uppercut",
    "rear uppercut": "uppercut",
}
# COCO-17 index → MediaPipe-33 index (person's own left/right in both).
COCO_FROM_MEDIAPIPE = [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP = 5, 6, 7, 8, 9, 10, 11, 12
FRAMES = 16  # every clip resampled to this many frames


def from_mediapipe(lms: np.ndarray) -> np.ndarray:
    """(n, 33, ≥2) MediaPipe image landmarks → (n, 17, 2) COCO keypoints."""
    out: np.ndarray = lms[:, COCO_FROM_MEDIAPIPE, :2]
    return out


def _resample(a: np.ndarray, n: int = FRAMES) -> np.ndarray:
    """(t, …) → (n, …) by linear interpolation over the clip."""
    if len(a) == n:
        return a
    src = np.linspace(0, 1, len(a))
    dst = np.linspace(0, 1, n)
    flat = a.reshape(len(a), -1)
    out = np.stack([np.interp(dst, src, flat[:, k]) for k in range(flat.shape[1])], axis=1)
    return out.reshape((n, *a.shape[1:]))


def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at b (degrees) per frame."""
    u, v = a - b, c - b
    cos = (u * v).sum(axis=1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-9)
    deg: np.ndarray = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    return deg


def features(clip: np.ndarray, *, mirror: bool = False) -> np.ndarray | None:
    """One row for a (t, 17, 2) clip, or None when it's too short or degenerate.
    `mirror` flips it left-right (data augmentation; the row is arm-agnostic anyway)."""
    if len(clip) < 3 or not np.all(np.isfinite(clip)):
        return None
    k = clip.astype(float).copy()
    if mirror:
        k[:, :, 0] = -k[:, :, 0]
    mid_sh = (k[:, L_SH] + k[:, R_SH]) / 2
    mid_hip = (k[:, L_HIP] + k[:, R_HIP]) / 2
    width = float(np.median(np.linalg.norm(k[:, L_SH] - k[:, R_SH], axis=1)))
    torso = float(np.median(np.linalg.norm(mid_sh - mid_hip, axis=1)))
    scale = max(width, 0.5 * torso)  # side-on, the shoulders overlap
    if scale < 1e-4:
        return None
    k = (k - mid_sh[0]) / scale
    k = _resample(k)
    paths = {
        side: float(np.linalg.norm(np.diff(k[:, wr], axis=0), axis=1).sum())
        for side, wr in (("left", L_WR), ("right", R_WR))
    }
    side = max(paths, key=lambda s: paths[s])
    sh, el, wr = (L_SH, L_EL, L_WR) if side == "left" else (R_SH, R_EL, R_WR)
    o_wr, o_sh = (R_WR, R_SH) if side == "left" else (L_WR, L_SH)
    rel_wr = k[:, wr] - k[:, sh]
    rel_el = k[:, el] - k[:, sh]
    # Facing direction varies with the camera: make x point the way this wrist reached.
    sign = (
        1.0 if (rel_wr[:, 0].max() - rel_wr[0, 0]) >= (rel_wr[0, 0] - rel_wr[:, 0].min()) else -1.0
    )
    rel_wr[:, 0] *= sign
    rel_el[:, 0] *= sign
    other = k[:, o_wr] - k[:, o_sh]
    other[:, 0] *= sign
    angle = _angle(k[:, sh], k[:, el], k[:, wr]) / 180.0
    speed = np.r_[0.0, np.linalg.norm(np.diff(k[:, wr], axis=0), axis=1)]
    disp = rel_wr - rel_wr[0]
    summary = [
        float(disp[:, 0].max()),
        float(-disp[:, 1].max()),  # image y grows down: up is negative
        float(disp[:, 1].max()),
        float(np.ptp(disp[:, 0])),
        float(np.ptp(disp[:, 1])),
        float(np.ptp(angle)),
        float(angle.min()),
        float(angle.max()),
        float(np.argmax(speed) / FRAMES),
        float(speed.max()),
        float(paths[side]),  # already in shoulder widths
        float(np.ptp(other[:, 0]) + np.ptp(other[:, 1])),
    ]
    return np.concatenate(
        [rel_wr.ravel(), rel_el.ravel(), angle, speed, other.ravel(), np.asarray(summary)]
    )
