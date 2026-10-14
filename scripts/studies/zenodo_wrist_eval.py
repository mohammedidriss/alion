"""The wrist punch-type model on other boxers: the Zenodo "Boxing punch data" set.

Manoharan, S., Boxing punch data, Zenodo, doi:10.5281/zenodo.14965635, CC BY 4.0
(elite boxers, IMU on the wrist under the glove, 200 Hz; one CSV per punch type:
gyr x/y/z in °/s, acc x/y/z in g; no time, boxer, stance or punch marks).

1. Resample to 100 Hz (mean of each pair of samples), find the punches with this
   project's wrist detector, and name them with the trained model (ADR-029),
   reading lead as the left hand and rear as the right (orthodox).
2. Where gravity points at guard in each set — whether the sensors' axes match.
3. A direction-free model (only the size of the acceleration and of the turn),
   trained on this project's takes and tested on these boxers.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/zenodo_wrist_eval.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from analyze import wrist_types as wt
from analyze.imu_punches import detect_punches
from api.services import wrist_type_model

ZENODO = wrist_type_model.EXTERNAL
FILES = wrist_type_model.EXTERNAL_FILES


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """t_ms and (n, 6) ax, ay, az, gx, gy, gz at 100 Hz."""
    return wrist_type_model.external_stream(path)


def at_guard(imu: np.ndarray) -> np.ndarray:
    """Mean acceleration while still (|a| within 0.05 g of 1 g): gravity in the sensor's frame."""
    mag = np.linalg.norm(imu[:, :3], axis=1)
    still = np.abs(mag - 1.0) < 0.05
    return imu[still, :3].mean(axis=0) if np.any(still) else np.full(3, np.nan)


def magnitude_only(x: np.ndarray) -> np.ndarray:
    """The features that don't depend on the sensor's orientation: the stats of |a|
    and |ω| (rows 6 and 7 of the per-channel block, 7 stats each)."""
    return x[:, 6 * 7 : 8 * 7]


def main() -> None:
    model = wrist_type_model._latest_model()
    if model is None:
        raise SystemExit("train the wrist type model first (Datasets page)")
    xs, ys, hands = [], [], []
    print(f"model v{model['version']} on {ZENODO.name}")
    for name, (hand, motion) in FILES.items():
        t, imu = load(ZENODO / name)
        found = detect_punches(t, imu[:, 0], imu[:, 1], imu[:, 2])
        rows = [wt.features(w, hand) for e in found if (w := wt.window(t, imu, e.t_ms)) is not None]
        if not rows:
            print(f"  {name}: no punches found")
            continue
        x = np.array(rows)
        pred = wt.classify(model["model"], x)
        right = sum(p == motion for p in pred)
        print(
            f"  {name:18} {len(t) / 100:6.0f} s  {len(rows):4} punches  "
            f"named {motion}: {right / len(rows):5.1%}   taken for {dict(Counter(pred))}"
        )
        xs.append(x)
        ys += [motion] * len(rows)
        hands += [hand] * len(rows)
    x_z, y_z = np.vstack(xs), np.array(ys)
    pred_z = np.array(wt.classify(model["model"], x_z))
    print(f"overall (model as trained here): {np.mean(pred_z == y_z):.1%} of {len(y_z)} punches")

    print("\ngravity at guard (g), x / y / z:")
    for name in ("Lead_jab.csv", "Rear_jab.csv"):
        _, imu = load(ZENODO / name)
        print(f"  Zenodo {name:14} {np.round(at_guard(imu), 2)}")
    x_ours, y_ours, _, _, _ = wrist_type_model.typed_punches()
    ours: dict[str, list[np.ndarray]] = {h: [] for h in ("left", "right")}
    for tj in sorted(Path("data/datasets").glob("*/takes/*/imu.csv"))[:6]:
        streams = wrist_type_model._imu_streams(tj.parent)
        for h, (_, imu) in streams.items():
            if len(imu):
                ours[h].append(at_guard(imu))
    for h, gs in ours.items():
        print(f"  this project {h:5} wrist   {np.round(np.nanmean(gs, axis=0), 2)}")

    print("\ndirection-free model (|a|, |ω| only), trained on this project's takes:")
    m = wt.fit(magnitude_only(x_ours), y_ours)
    pred_m = np.array(wt.classify(m, magnitude_only(x_z)))
    print(f"  on the Zenodo boxers: {np.mean(pred_m == y_z):.1%} of {len(y_z)}")
    for motion in wt.MOTIONS:
        sel = y_z == motion
        print(
            f"    {motion:9} recall {np.mean(pred_m[sel] == motion):5.1%}   taken for {dict(Counter(pred_m[sel].tolist()))}"
        )


if __name__ == "__main__":
    main()
