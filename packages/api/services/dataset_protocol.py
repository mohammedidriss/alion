"""Dataset recording protocol — self-labeling takes for the RQ2 punch dataset.

The fighter works through fixed blocks (30 jabs, 30 crosses, …) while the coach
marks each block's start and end on the take screen. Every punch inside a block
has a known type, and the wrist IMUs give each one's exact time, so a take
comes out labeled with no hand-tagging:

    block (type + lead/rear)  ×  IMU bursts on that wrist  →  {take}/labels.json

Everything lives in the take's folder (ADR-013); this side owns two files:

    protocol.json   block markers, per-block QA counts, label provenance
    labels.json     [{t_ms, hand, punch_type}] — what studies.evaluation reads

and reads `imu.csv`, which `imu_runner` appends to while the take records.
Block times are on the take timeline (ms since the cameras' synchronized start;
takes can't pause), the same axis as imu.csv, pose and the clips. The
methodology is in docs/studies/RQ2_DATASET_PROTOCOL.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from analyze.imu_punches import MIN_GAP_MS, SMOOTH_MS, THRESHOLD_G, detect_punches

Side = Literal["lead", "rear", "both"]
Kind = Literal["typed", "negative", "free"]
HANDS = ("left", "right")


@dataclass(frozen=True)
class BlockSpec:
    key: str
    title: str
    kind: Kind
    punch_type: str | None = None  # "jab" | "cross" | "hook" | "uppercut"
    side: Side | None = None
    reps: int | None = None
    duration_s: int | None = None
    hint: str = ""


# Six typed blocks give the 6-class type classifier (H2b) its classes; the
# negatives teach the detector what isn't a punch; free shadowboxing is the
# realistic held-out test material.
PLAN: list[BlockSpec] = [
    BlockSpec("jab", "Jab", "typed", "jab", "lead", reps=30, hint="Return to guard each time"),
    BlockSpec("cross", "Cross", "typed", "cross", "rear", reps=30),
    BlockSpec("lead_hook", "Lead hook", "typed", "hook", "lead", reps=30),
    BlockSpec("rear_hook", "Rear hook", "typed", "hook", "rear", reps=30),
    BlockSpec("lead_uppercut", "Lead uppercut", "typed", "uppercut", "lead", reps=30),
    BlockSpec("rear_uppercut", "Rear uppercut", "typed", "uppercut", "rear", reps=30),
    BlockSpec(
        "negatives",
        "No punches",
        "negative",
        duration_s=120,
        hint="Guard, footwork, slips, rolls, feints — anything but a punch",
    ),
    BlockSpec(
        "free",
        "Free shadowboxing",
        "free",
        side="both",
        duration_s=120,
        hint="Combinations at your own pace — kept for testing",
    ),
]
SPECS = {s.key: s for s in PLAN}


class ProtocolError(ValueError):
    """A request that doesn't fit the protocol state (→ 409)."""


# --------------------------------------------------------------------------
# protocol.json
# --------------------------------------------------------------------------

_lock = threading.Lock()


def protocol_path(folder: Path) -> Path:
    return folder / "protocol.json"


def labels_path(folder: Path) -> Path:
    return folder / "labels.json"


def load(folder: Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(protocol_path(folder).read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("blocks", [])
    return data


def _write(path: Path, text: str) -> None:
    """Atomic replace, so the take screen's poll never reads half a file."""
    with _lock:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)


def save(folder: Path, data: dict[str, Any]) -> None:
    _write(protocol_path(folder), json.dumps(data, indent=2) + "\n")


def active_index(data: dict[str, Any]) -> int | None:
    for i, b in enumerate(data["blocks"]):
        if b.get("t_end_ms") is None and not b.get("discarded"):
            return i
    return None


def start_block(data: dict[str, Any], key: str, now_ms: float, imu_byte: int = 0) -> dict[str, Any]:
    """Open block `key` at `now_ms`, closing any block still open. `imu_byte` is
    imu.csv's size at that moment, so a live count reads only the block's rows."""
    if key not in SPECS:
        raise ProtocolError(f"unknown block {key!r}")
    end_block(data, now_ms, missing_ok=True)
    data["blocks"].append(
        {"key": key, "t_start_ms": max(0.0, now_ms), "t_end_ms": None, "imu_byte": imu_byte}
    )
    return data


def end_block(data: dict[str, Any], now_ms: float, *, missing_ok: bool = False) -> dict[str, Any]:
    i = active_index(data)
    if i is None:
        if missing_ok:
            return data
        raise ProtocolError("no block is running")
    block = data["blocks"][i]
    block["t_end_ms"] = max(block["t_start_ms"], now_ms)
    return data


def discard_block(data: dict[str, Any], index: int) -> dict[str, Any]:
    """Drop a block from the labels (a redo); it stays in the file for the record."""
    if not 0 <= index < len(data["blocks"]):
        raise ProtocolError(f"no block #{index}")
    data["blocks"][index]["discarded"] = True
    return data


# --------------------------------------------------------------------------
# imu.csv
# --------------------------------------------------------------------------

Wrists = dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]


def imu_size(folder: Path) -> int:
    try:
        return (folder / "imu.csv").stat().st_size
    except OSError:
        return 0


def read_imu(folder: Path, start_byte: int = 0) -> Wrists:
    """{hand: (t_ms, ax, ay, az)} from imu.csv, starting at `start_byte`.

    The runner appends while the take records, so a trailing line without its
    newline (mid-write) is skipped rather than half-parsed.
    """
    cols: dict[str, list[list[float]]] = {h: [] for h in HANDS}
    try:
        with (folder / "imu.csv").open("rb") as f:
            f.seek(start_byte)
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        raw = ""
    for line in raw.split("\n")[:-1]:  # the last piece is "" or an unfinished line
        parts = line.split(",")
        if len(parts) < 5 or parts[1] not in cols:
            continue  # header or a malformed line
        try:
            cols[parts[1]].append(
                [float(parts[0]), float(parts[2]), float(parts[3]), float(parts[4])]
            )
        except ValueError:
            continue
    out: Wrists = {}
    for hand, rows in cols.items():
        if rows:
            a = np.asarray(rows)
            out[hand] = (a[:, 0], a[:, 1], a[:, 2], a[:, 3])
    return out


# --------------------------------------------------------------------------
# Labeling
# --------------------------------------------------------------------------


def lead_hand(stance: str | None) -> str:
    """Orthodox leads with the left. Switch fighters are labeled as orthodox — record
    each stance as its own take."""
    return "right" if stance == "southpaw" else "left"


def expected_hands(spec: BlockSpec, stance: str | None) -> set[str]:
    if spec.side == "both":
        return set(HANDS)
    if spec.side is None:
        return set()
    lead = lead_hand(stance)
    rear = "right" if lead == "left" else "left"
    return {lead if spec.side == "lead" else rear}


@dataclass
class BlockResult:
    index: int
    key: str
    detected: int  # punches on the expected wrist(s)
    off_hand: int  # bursts on the other wrist (or any burst in the no-punch block)
    labels: list[dict[str, Any]]


def label_block(
    wrists: Wrists,
    index: int,
    block: dict[str, Any],
    stance: str | None,
    *,
    until_ms: float | None = None,
) -> BlockResult:
    """Punches inside one block, labeled with its type and hand. `until_ms` closes
    a still-running block for a live count."""
    spec = SPECS[block["key"]]
    t_end = block["t_end_ms"] if block.get("t_end_ms") is not None else until_ms
    if t_end is None:
        return BlockResult(index, spec.key, 0, 0, [])
    wanted = expected_hands(spec, stance)
    detected, off_hand = 0, 0
    labels: list[dict[str, Any]] = []
    for hand, (t, ax, ay, az) in wrists.items():
        inside = (t >= block["t_start_ms"]) & (t <= t_end)
        events = detect_punches(t[inside], ax[inside], ay[inside], az[inside])
        if spec.kind == "negative" or hand not in wanted:
            off_hand += len(events)  # a QA count, never a label
            continue
        detected += len(events)
        labels += [
            {"t_ms": round(e.t_ms, 1), "hand": hand, "punch_type": spec.punch_type} for e in events
        ]
    return BlockResult(index, spec.key, detected, off_hand, labels)


def live_count(
    folder: Path, data: dict[str, Any], stance: str | None, now_ms: float
) -> BlockResult | None:
    """The open block's count so far, reading only imu.csv rows written since it began."""
    i = active_index(data)
    if i is None:
        return None
    block = data["blocks"][i]
    return label_block(
        read_imu(folder, block.get("imu_byte", 0)), i, block, stance, until_ms=now_ms
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def labels_edited(folder: Path, data: dict[str, Any]) -> bool:
    """True if labels.json exists and isn't what we last wrote — someone reviewed
    or hand-made it, so regenerating would throw their work away."""
    path = labels_path(folder)
    if not path.exists():
        return False
    written = (data.get("labels") or {}).get("sha256")
    return written != _digest(path.read_text())


def generate_labels(
    folder: Path, data: dict[str, Any], stance: str | None, *, overwrite: bool = False
) -> list[BlockResult]:
    """Label every finished, non-discarded block into labels.json, and record the
    per-block counts and provenance in `data` (the caller saves it).

    Refuses (ProtocolError) to replace labels someone edited, unless `overwrite`.
    """
    if labels_edited(folder, data) and not overwrite:
        raise ProtocolError(
            "The labels were edited after they were generated — regenerating would "
            "replace that review. Pass overwrite to do it anyway."
        )
    wrists = read_imu(folder)
    results = [
        label_block(wrists, i, b, stance)
        for i, b in enumerate(data["blocks"])
        if not b.get("discarded") and b.get("t_end_ms") is not None
    ]
    labels = sorted((lab for r in results for lab in r.labels), key=lambda lab: lab["t_ms"])
    for r in results:
        data["blocks"][r.index]["detected"] = r.detected
        data["blocks"][r.index]["off_hand"] = r.off_hand
    text = json.dumps(labels, indent=2)
    _write(labels_path(folder), text)
    data["labels"] = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "count": len(labels),
        "stance": stance,
        "sha256": _digest(text),
        "detector": {
            "name": "analyze.imu_punches",
            "threshold_g": THRESHOLD_G,
            "min_gap_ms": MIN_GAP_MS,
            "smooth_ms": SMOOTH_MS,
        },
    }
    return results


def plan_out() -> list[dict[str, Any]]:
    return [asdict(s) for s in PLAN]
