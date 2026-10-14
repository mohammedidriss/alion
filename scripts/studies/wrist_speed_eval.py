"""Does the wrist sensors' speed estimate agree with the cameras' punch speed?

For every punch the wrists and the cameras both saw (a cross-check's "both"
punches, which carry the cameras' speed), estimate the speed from the wrist
(`analyze.wrist_speed`) and compare. Neither is ground truth — the cameras' speed
comes from monocular pose — so this measures agreement: correlation, the typical
ratio, and the error around it. Reads dataset takes (imu.csv + crosscheck.json)
read-only.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/wrist_speed_eval.py [--datasets data/datasets]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from analyze.wrist_speed import peak_speed


def pairs(datasets: Path) -> list[tuple[float, float, str, str]]:
    """(wrist estimate, camera speed, hand, take id)."""
    out: list[tuple[float, float, str, str]] = []
    for xc_path in sorted(datasets.glob("*/takes/*/crosscheck.json")):
        folder = xc_path.parent
        if not (folder / "imu.csv").exists():
            continue
        both = [
            p
            for p in json.loads(xc_path.read_text()).get("punches", [])
            if p.get("source") == "both" and p.get("speed_ms")
        ]
        if not both:
            continue
        rows: dict[str, list[list[float]]] = {"left": [], "right": []}
        with (folder / "imu.csv").open(newline="") as f:
            for r in csv.DictReader(f):
                if r["hand"] in rows:
                    rows[r["hand"]].append(
                        [
                            float(r[k])
                            for k in ("t_ms", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps")
                        ]
                    )
        streams = {h: np.array(sorted(rr), dtype=float).reshape(-1, 7) for h, rr in rows.items()}
        for p in both:
            a = streams.get(p["hand"])
            if a is None or len(a) < 20:
                continue
            est = peak_speed(a[:, 0], a[:, 1:4], a[:, 4:7], float(p["t_ms"]))
            if est is not None:
                out.append((est, float(p["speed_ms"]), p["hand"], folder.name))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    args = ap.parse_args()
    data = pairs(args.datasets)
    if len(data) < 10:
        print(f"only {len(data)} punches seen by both — not enough to compare")
        return
    wrist = np.array([d[0] for d in data])
    camera = np.array([d[1] for d in data])
    pearson = float(np.corrcoef(wrist, camera)[0, 1])
    ranks = lambda v: np.argsort(np.argsort(v))  # noqa: E731
    spearman = float(np.corrcoef(ranks(wrist), ranks(camera))[0, 1])
    ratio = wrist / camera
    scaled = wrist / float(np.median(ratio))
    mape = float(np.median(np.abs(scaled - camera) / camera))
    print(
        f"{len(data)} punches seen by the wrists and the cameras, {len({d[3] for d in data})} takes"
    )
    print(
        f"wrist estimate  median {np.median(wrist):.2f} m/s  (p10 {np.percentile(wrist, 10):.2f}, p90 {np.percentile(wrist, 90):.2f})"
    )
    print(
        f"camera speed    median {np.median(camera):.2f} m/s  (p10 {np.percentile(camera, 10):.2f}, p90 {np.percentile(camera, 90):.2f})"
    )
    print(f"correlation     Pearson {pearson:.2f}, Spearman {spearman:.2f}")
    print(
        f"wrist / camera  median {np.median(ratio):.2f}  (p10 {np.percentile(ratio, 10):.2f}, p90 {np.percentile(ratio, 90):.2f})"
    )
    print(f"after scaling by that median: typical error {mape:.0%} of the camera speed")
    for h in ("left", "right"):
        m = np.array([d[2] == h for d in data])
        if m.sum() >= 5:
            print(
                f"  {h:5}: n={m.sum()}, Pearson {np.corrcoef(wrist[m], camera[m])[0, 1]:.2f}, median ratio {np.median(ratio[m]):.2f}"
            )


if __name__ == "__main__":
    main()
