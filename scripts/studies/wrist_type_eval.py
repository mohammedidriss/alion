"""How well the wrist sensors alone tell a straight from a hook from an uppercut
(ADR-028) — the same scoring the wrist type model saves with each version
(services.wrist_type_model), here without saving a model.

Reads every completed dataset take with wrist data (read-only). Two tests, both
on takes the model never trained on:

1. take-held-out: 5-fold cross-validation grouped by take;
2. combos: trained on single-type blocks only, tested on the combination blocks.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/wrist_type_eval.py [--datasets data/datasets]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from analyze import wrist_types as wt
from api.services.wrist_type_model import score, typed_punches


def show(name: str, result: dict[str, object]) -> None:
    print(f"\n== {name}: {result['punches']} punches")
    print(
        f"accuracy {result['accuracy']:.1%}   (always the commonest motion: {result['majority_share']:.1%})"
    )
    recall = result["recall"]
    confusion = result["confusion"]
    assert isinstance(recall, dict) and isinstance(confusion, dict)
    for c in wt.MOTIONS:
        r = recall[c]
        print(f"  {c:9} recall {('—' if r is None else f'{r:.1%}'):>6}   taken for: {confusion[c]}")
    by_hand = result["by_hand"]
    assert isinstance(by_hand, dict)
    print("  by hand: " + ", ".join(f"{h} {v:.1%}" for h, v in by_hand.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--out", type=Path, default=None, help="write the results as JSON")
    args = ap.parse_args()
    from sklearn.model_selection import GroupKFold

    x, y, hands, groups, meta = typed_punches(args.datasets)
    kinds = np.array(meta.pop("kinds"))
    print(f"{len(y)} typed punches from {meta['takes']} takes: {dict(Counter(y.tolist()))}")
    pred = np.empty_like(y)
    for train, test in GroupKFold(n_splits=5).split(x, y, groups):
        pred[test] = wt.classify(wt.fit(x[train], y[train]), x[test])
    results: dict[str, object] = {"take_held_out": score(y, pred, hands)}
    show("Takes held out (5-fold, by take)", results["take_held_out"])  # type: ignore[arg-type]
    single, combo = kinds == "single", kinds == "combo"
    if np.any(combo) and np.any(single):
        model = wt.fit(x[single], y[single])
        results["combos"] = score(y[combo], np.array(wt.classify(model, x[combo])), hands[combo])
        show("Combos (trained on single-type blocks only)", results["combos"])  # type: ignore[arg-type]
    if args.out:
        args.out.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
