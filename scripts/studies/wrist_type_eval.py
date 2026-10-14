"""How well the wrist sensors alone tell a straight from a hook from an uppercut.

Reads every completed dataset take with wrist data (read-only): each typed label
(t_ms, hand, jab|cross|hook|uppercut) becomes one punch, its motion the class.
Two tests, both on takes the model never trained on:

1. take-held-out: 5-fold cross-validation grouped by take;
2. combos: trained on single-type blocks only, tested on the combination blocks
   (jab-cross, cross-hook, …) where punch types mix as they do in training.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/wrist_type_eval.py [--datasets data/datasets]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from analyze import wrist_types as wt


def load(datasets: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """x, motion, hand, take id, block kind ("combo" or "single")."""
    xs, ys, hands, groups, kinds = [], [], [], [], []
    for tj in sorted(datasets.glob("*/takes/*/take.json")):
        folder = tj.parent
        take = json.loads(tj.read_text())
        if take.get("status") != "completed" or not (folder / "imu.csv").exists():
            continue
        labels = (
            json.loads((folder / "labels.json").read_text())
            if (folder / "labels.json").exists()
            else []
        )
        typed = [lab for lab in labels if lab.get("punch_type") in wt.TYPE_TO_MOTION]
        if not typed:
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
        streams = {}
        for h, rr in rows.items():
            a = np.array(sorted(rr), dtype=float).reshape(-1, 7)
            streams[h] = (a[:, 0], a[:, 1:])
        kind = "combo" if str(take.get("block") or "").startswith("combo") else "single"
        for lab in typed:
            t, imu = streams[lab["hand"]]
            win = wt.window(t, imu, float(lab["t_ms"])) if len(t) else None
            if win is None:
                continue
            xs.append(wt.features(win, lab["hand"]))
            ys.append(wt.TYPE_TO_MOTION[lab["punch_type"]])
            hands.append(lab["hand"])
            groups.append(take["take_id"])
            kinds.append(kind)
    return np.array(xs), np.array(ys), np.array(hands), np.array(groups), np.array(kinds)


def report(name: str, y: np.ndarray, pred: np.ndarray, hands: np.ndarray) -> dict[str, object]:
    labels = list(wt.MOTIONS)
    acc = float(np.mean(y == pred))
    per_class = {c: float(np.mean(pred[y == c] == c)) if np.any(y == c) else None for c in labels}
    cm = {c: dict(Counter(pred[y == c].tolist())) for c in labels}
    per_hand = {
        h: float(np.mean(y[hands == h] == pred[hands == h]))
        for h in ("left", "right")
        if np.any(hands == h)
    }
    majority = Counter(y.tolist()).most_common(1)[0]
    print(f"\n== {name}: {len(y)} punches")
    print(f"accuracy {acc:.1%}   (always guessing '{majority[0]}': {majority[1] / len(y):.1%})")
    for c in labels:
        r = per_class[c]
        print(f"  {c:9} recall {('—' if r is None else f'{r:.1%}'):>6}   taken for: {cm[c]}")
    print("  by hand: " + ", ".join(f"{h} {v:.1%}" for h, v in per_hand.items()))
    return {"n": len(y), "accuracy": acc, "recall": per_class, "confusion": cm, "by_hand": per_hand}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--out", type=Path, default=None, help="write the results as JSON")
    args = ap.parse_args()
    from sklearn.model_selection import GroupKFold

    x, y, hands, groups, kinds = load(args.datasets)
    print(
        f"{len(y)} typed punches from {len(set(groups.tolist()))} takes: {dict(Counter(y.tolist()))}"
    )
    results: dict[str, object] = {}

    pred = np.empty_like(y)
    for train, test in GroupKFold(n_splits=5).split(x, y, groups):
        pred[test] = wt.classify(wt.fit(x[train], y[train]), x[test])
    results["take_held_out"] = report("Takes held out (5-fold, by take)", y, pred, hands)

    single, combo = kinds == "single", kinds == "combo"
    if np.any(combo) and np.any(single):
        model = wt.fit(x[single], y[single])
        results["combos"] = report(
            "Combos (trained on single-type blocks only)",
            y[combo],
            np.array(wt.classify(model, x[combo])),
            hands[combo],
        )
    if args.out:
        args.out.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
