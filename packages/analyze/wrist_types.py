"""Punch motion from one wrist sensor: straight, hook or uppercut.

The camera's type classifier (ADR-020) reads the arm's path in the pose; this
reads the same motion where it happens — the wrist's acceleration and rotation
around each punch. A straight drives along the forearm and turns it over; a hook
swings it across with the elbow out; an uppercut drives it up and returns. Jab
or cross then follows from the hand and the stance, as for the cameras.

`window` cuts a fixed grid of samples around a punch (acceleration in g,
rotation in °/s), `features` turns it into one row; `fit` / `classify` wrap a
scikit-learn model (the "ml" extra, imported only when used). Pure numpy
otherwise — the evaluation lives in scripts/studies/wrist_type_eval.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np

MOTIONS = ("straight", "hook", "uppercut")
TYPE_TO_MOTION = {"jab": "straight", "cross": "straight", "hook": "hook", "uppercut": "uppercut"}

BEFORE_MS = 250.0  # the launch
AFTER_MS = 350.0  # lock-out, and an uppercut's return
STEP_MS = 10.0  # the sensors' 100 Hz
GRID = np.arange(-BEFORE_MS, AFTER_MS + STEP_MS / 2, STEP_MS)  # 61 points
AT = round(BEFORE_MS / STEP_MS)  # the punch's own sample on the grid (t = 0)
MAX_GAP_MS = 60.0  # a window with a longer dropout is unusable


def window(t_ms: np.ndarray, imu: np.ndarray, at_ms: float) -> np.ndarray | None:
    """(len(GRID), 6) — ax, ay, az (g), gx, gy, gz (°/s) on the grid around `at_ms`,
    from one wrist's samples (`t_ms` sorted, `imu` (n, 6)). None near a dropout."""
    lo, hi = at_ms - BEFORE_MS, at_ms + AFTER_MS
    i0, i1 = int(np.searchsorted(t_ms, lo)), int(np.searchsorted(t_ms, hi, side="right"))
    if i1 - i0 < len(GRID) // 2:
        return None
    seg_t = t_ms[max(0, i0 - 1) : i1 + 1]
    if (
        seg_t[0] > lo + MAX_GAP_MS
        or seg_t[-1] < hi - MAX_GAP_MS
        or np.max(np.diff(seg_t)) > MAX_GAP_MS
    ):
        return None
    seg = imu[max(0, i0 - 1) : i1 + 1]
    g = GRID + at_ms
    return np.stack([np.interp(g, seg_t, seg[:, c]) for c in range(6)], axis=1)


def features(win: np.ndarray, hand: str) -> np.ndarray:
    """One row per punch: shape statistics of each channel and of the magnitudes,
    when things peak, how far the forearm turned, and the window downsampled."""
    acc, gyr = win[:, :3], win[:, 3:]
    a_mag = np.linalg.norm(acc, axis=1)
    w_mag = np.linalg.norm(gyr, axis=1)
    rel = GRID / (BEFORE_MS + AFTER_MS)  # time as a fraction of the window
    launch = GRID <= 0
    rows: list[float] = []
    for ch in [*win.T, a_mag, w_mag]:
        rows += [
            float(ch.mean()),
            float(ch.std()),
            float(ch.min()),
            float(ch.max()),
            float(rel[int(np.argmin(ch))]),
            float(rel[int(np.argmax(ch))]),
            float(ch[AT]),  # at the punch
        ]
    # How far the forearm turned (°), over the launch and over the whole window.
    turned_launch = gyr[launch].sum(axis=0) * STEP_MS / 1000.0
    turned_all = gyr.sum(axis=0) * STEP_MS / 1000.0
    rows += [*turned_launch.tolist(), *turned_all.tolist()]
    # Gravity before the launch (the guard's tilt) — the sensor's own frame.
    rows += acc[:5].mean(axis=0).tolist()
    # The window itself, every 30 ms.
    rows += win[::3].ravel().tolist()
    rows.append(1.0 if hand == "right" else 0.0)
    return np.asarray(rows, dtype=float)


def fit(x: np.ndarray, y: np.ndarray, *, seed: int = 0) -> Any:
    import sklearn.ensemble  # type: ignore[import-untyped, import-not-found, unused-ignore]

    model = sklearn.ensemble.HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, random_state=seed
    )
    model.fit(x, y)
    return model


def classify(model: Any, x: np.ndarray) -> list[str]:
    return [str(v) for v in model.predict(x)]
