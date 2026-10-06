"""Dataset export — the manifest and splits the training scripts read (ADR-013).

`build_manifest` turns a dataset's takes into one JSON document:

- **takes**: every completed take with its files (clips + start offsets, pose,
  imu.csv, hr.csv, labels.json) and its protocol blocks with QA counts.
- **splits**: train / val / test as time segments of takes.
- **warnings**: what a reviewer should fix before trusting the numbers.

Splits follow docs/studies/RQ2_DATASET_PROTOCOL.md §7:

- **by_fighter** (3+ fighters): whole fighters are held out, so no person is in
  both train and test. A seeded shuffle makes the split stable across exports.
- **pilot** (1–2 fighters): there's no fighter to hold out, so each take is
  split by block — the scripted blocks (and the no-punch block, for negatives)
  train, free shadowboxing tests. Fine for proving the pipeline; it can't
  support a claim that the model generalizes to other people.

Fighters appear by id only — names stay in the database.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from api.services import dataset_protocol as proto
from api.services import dataset_store

BY_FIGHTER_MIN = 3


@dataclass(frozen=True)
class TakeRef:
    take_id: UUID
    fighter_id: UUID
    status: str
    duration_ms: float | None


def _take_entry(ref: TakeRef, folder: Path, root: Path) -> dict[str, Any]:
    data = proto.load(folder)
    take = dataset_store.read_take_json(folder)
    labels: dict[str, Any] | None = None
    if proto.labels_path(folder).exists():
        try:
            count = len(json.loads(proto.labels_path(folder).read_text()))
        except ValueError:
            count = 0
        labels = {
            "path": "labels.json",
            "count": count,
            "reviewed": proto.labels_edited(folder, data),
        }
    blocks = [
        {k: b.get(k) for k in ("key", "t_start_ms", "t_end_ms", "detected", "off_hand")}
        for b in data["blocks"]
        if not b.get("discarded") and b.get("t_end_ms") is not None
    ]
    return {
        "take_id": str(ref.take_id),
        "fighter_id": str(ref.fighter_id),
        "stance": take.get("stance"),
        "duration_ms": ref.duration_ms,
        "folder": str(folder.relative_to(root)),
        "video": [
            {
                "device_id": c["device_id"],
                "path": f"video/{c['device_id']}.{c['ext']}",
                "start_offset_ms": c["start_offset_ms"],
            }
            for c in dataset_store.clips(folder)
        ],
        "pose": sorted(f"pose/{p.name}" for p in (folder / "pose").glob("*.parquet")),
        "imu": "imu.csv" if (folder / "imu.csv").exists() else None,
        "hr": "hr.csv" if (folder / "hr.csv").exists() else None,
        "labels": labels,
        "blocks": blocks,
        # imu.csv is raw: when True its "left" rows are the right wrist and vice
        # versa (sensors worn swapped); labels.json is already corrected.
        "imu_hands_swapped": proto.hands_swapped(data),
        "swap_evidence": proto.swap_evidence(data, proto.camera_hands(folder)),
    }


def _whole(entry: dict[str, Any]) -> dict[str, Any]:
    return {"take_id": entry["take_id"], "t_start_ms": 0.0, "t_end_ms": entry["duration_ms"]}


def _split_by_fighter(
    entries: list[dict[str, Any]], seed: str, test_frac: float, val_frac: float
) -> dict[str, list[dict[str, Any]]]:
    fighters = sorted({e["fighter_id"] for e in entries})
    random.Random(seed).shuffle(fighters)
    n_test = max(1, math.ceil(len(fighters) * test_frac))
    n_val = max(1, math.ceil(len(fighters) * val_frac))
    test, val = set(fighters[:n_test]), set(fighters[n_test : n_test + n_val])
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}
    for e in entries:
        name = "test" if e["fighter_id"] in test else "val" if e["fighter_id"] in val else "train"
        splits[name].append(_whole(e))
    return splits


def _split_pilot(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}
    for e in entries:
        for b in e["blocks"]:
            kind = proto.SPECS[b["key"]].kind
            splits["test" if kind == "free" else "train"].append(
                {
                    "take_id": e["take_id"],
                    "t_start_ms": b["t_start_ms"],
                    "t_end_ms": b["t_end_ms"],
                    "block": b["key"],
                }
            )
    return splits


def build_manifest(
    dataset_id: UUID,
    protocol: str | None,
    takes: list[TakeRef],
    *,
    test_frac: float = 0.2,
    val_frac: float = 0.2,
) -> dict[str, Any]:
    root = dataset_store.dataset_dir(dataset_id)
    entries: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    warnings: list[str] = []
    for ref in takes:
        folder = dataset_store.take_dir(ref.take_id)
        if ref.status != "completed":
            excluded.append({"take_id": str(ref.take_id), "reason": ref.status})
            continue
        if folder is None:
            excluded.append({"take_id": str(ref.take_id), "reason": "folder missing"})
            continue
        entries.append(_take_entry(ref, folder, root))

    for e in entries:
        tid = e["take_id"][:8]
        if not e["video"]:
            warnings.append(f"take {tid}: no video")
        if e["imu"] is None:
            warnings.append(f"take {tid}: no wrist-sensor data — nothing to label from")
        if e["labels"] is None:
            warnings.append(f"take {tid}: no labels — run the protocol or regenerate")
        elif not e["labels"]["reviewed"]:
            warnings.append(f"take {tid}: labels are unreviewed auto-labels")
        if e["imu_hands_swapped"]:
            warnings.append(
                f"take {tid}: sensors were worn on swapped wrists — imu.csv's hand column "
                "is reversed (see imu_hands_swapped); labels are corrected"
            )
        if e["swap_evidence"]:
            warnings.append(
                f"take {tid}: wrist sensors look swapped ({'; '.join(e['swap_evidence'])}) "
                "— check it and use Swap wrists on the take"
            )

    n_fighters = len({e["fighter_id"] for e in entries})
    if n_fighters >= BY_FIGHTER_MIN:
        strategy = "by_fighter"
        splits = _split_by_fighter(entries, str(dataset_id), test_frac, val_frac)
    else:
        strategy = "pilot"
        splits = _split_pilot(entries)
        if entries:
            warnings.append(
                f"pilot split: {n_fighters} fighter(s), so nobody is held out — scripted "
                "blocks train, free shadowboxing tests; results can't claim generalization "
                f"to other people (needs {BY_FIGHTER_MIN}+ fighters)"
            )

    return {
        "dataset_id": str(dataset_id),
        "protocol": protocol,
        "exported_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "split_strategy": strategy,
        "counts": {
            "takes": len(entries),
            "fighters": n_fighters,
            "labels": sum((e["labels"] or {}).get("count", 0) for e in entries),
        },
        "takes": entries,
        "splits": splits,
        "excluded": excluded,
        "warnings": warnings,
    }


def write_manifest(dataset_id: UUID, manifest: dict[str, Any]) -> Path:
    """{dataset}/export/manifest.json — what the training scripts read."""
    out = dataset_store.dataset_dir(dataset_id) / "export" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("manifest.json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(tmp, out)
    return out
