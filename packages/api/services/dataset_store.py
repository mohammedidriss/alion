"""Take folders — the file side of datasets (ADR-013).

    data/datasets/{dataset_id}/takes/{take_id}/
      take.json        written only here
      video/{device}.webm + {device}.json (clip start offset)
      pose/{device}.parquet
      imu.csv          t_ms,hand,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps
      hr.csv           t_ms,rr_ms,hr_bpm
      protocol.json    written only by the protocol side
      labels.json      written only by the protocol side

A take's timeline is the cameras' synchronized start (t = 0); takes can't be
paused, so `t_ms` is simply wall ms − t0. Lives in `api/services/` (composition
root) next to the runners that stream into these files.
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from store import HRSampleRow, IMUSampleRow

DATASETS_DIR = Path("data/datasets")
IMU_HEADER = "t_ms,hand,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps"
HR_HEADER = "t_ms,rr_ms,hr_bpm"

_json_lock = threading.Lock()


def dataset_dir(dataset_id: UUID) -> Path:
    return DATASETS_DIR / str(dataset_id)


def take_dir(take_id: UUID) -> Path | None:
    """The take's folder, or None if `take_id` isn't a dataset take (e.g. a session)."""
    hits = list(DATASETS_DIR.glob(f"*/takes/{take_id}"))
    return hits[0] if hits else None


def create_take_dir(dataset_id: UUID, take_id: UUID, take: dict[str, Any]) -> Path:
    folder = dataset_dir(dataset_id) / "takes" / str(take_id)
    (folder / "video").mkdir(parents=True, exist_ok=True)
    (folder / "pose").mkdir(exist_ok=True)
    write_take_json(folder, take)
    return folder


def read_take_json(folder: Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads((folder / "take.json").read_text())
        return data
    except (OSError, ValueError):
        return {}


def write_take_json(folder: Path, data: dict[str, Any]) -> None:
    """Atomic replace, so a reader never sees a half-written file."""
    with _json_lock:
        tmp = folder / "take.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, default=str) + "\n")
        os.replace(tmp, folder / "take.json")


def update_take_json(folder: Path, **fields: Any) -> dict[str, Any]:
    with _json_lock:
        data = read_take_json(folder)
        data.update(fields)
        tmp = folder / "take.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, default=str) + "\n")
        os.replace(tmp, folder / "take.json")
        return data


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------


def clip_path(folder: Path, device_id: str, ext: str) -> Path:
    return folder / "video" / f"{device_id}{ext}"


def clip_meta_path(folder: Path, device_id: str) -> Path:
    return folder / "video" / f"{device_id}.json"


def pose_path(folder: Path, device_id: str) -> Path:
    return folder / "pose" / f"{device_id}.parquet"


def clips(folder: Path) -> list[dict[str, Any]]:
    """[{device_id, ext, bytes, start_offset_ms}] for each recorded clip."""
    out: list[dict[str, Any]] = []
    for p in sorted((folder / "video").glob("*")):
        if p.suffix not in (".webm", ".mp4") or p.stat().st_size == 0:
            continue
        offset = None
        try:
            offset = float(
                json.loads(clip_meta_path(folder, p.stem).read_text())["start_offset_ms"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass
        out.append(
            {
                "device_id": p.stem,
                "ext": p.suffix[1:],
                "bytes": p.stat().st_size,
                "start_offset_ms": offset,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Sensor streams → CSV (the runners' row sinks for a take)
# ---------------------------------------------------------------------------


def _appender(path: Path, header: str) -> Callable[[list[str]], None]:
    lock = threading.Lock()

    def append(lines: list[str]) -> None:
        if not lines:
            return
        with lock:
            new = not path.exists()
            with path.open("a") as f:
                if new:
                    f.write(header + "\n")
                f.write("\n".join(lines) + "\n")

    return append


def imu_writer(folder: Path) -> Callable[[list[IMUSampleRow]], None]:
    """Row sink for `imu_runner`: appends to the take's imu.csv."""
    append = _appender(folder / "imu.csv", IMU_HEADER)

    def write(rows: list[IMUSampleRow]) -> None:
        append(
            [
                f"{r.t_ms:.2f},{r.hand},{r.ax_g:.4f},{r.ay_g:.4f},{r.az_g:.4f},"
                f"{r.gx_dps:.2f},{r.gy_dps:.2f},{r.gz_dps:.2f}"
                for r in rows
            ]
        )

    return write


def hr_writer(
    folder: Path, t0_fn: Callable[[], float | None]
) -> Callable[[list[HRSampleRow]], None]:
    """Row sink for `hrv_runner` streaming with `wall_clock=True` (each row's t_ms is
    the beat's arrival, epoch ms). `t0_fn` gives the cameras' start: beats before it
    — the strap connects before the take starts — aren't stored; later ones land on
    the take timeline (to about a second, which heart rate needs)."""
    append = _appender(folder / "hr.csv", HR_HEADER)

    def write(rows: list[HRSampleRow]) -> None:
        t0 = t0_fn()
        if t0 is None:
            return
        append([f"{r.t_ms - t0:.1f},{r.rr_ms:.1f},{r.hr_bpm:.1f}" for r in rows if r.t_ms >= t0])

    return write


def _count_rows(path: Path) -> int:
    try:
        with path.open() as f:
            return max(0, sum(1 for _ in f) - 1)  # minus the header
    except OSError:
        return 0


def recent_bpm(folder: Path, n: int = 60) -> list[float]:
    """The last `n` heart-rate values, oldest first."""
    try:
        with (folder / "hr.csv").open() as f:
            tail = deque(f, maxlen=n)
    except OSError:
        return []
    out: list[float] = []
    for line in tail:
        parts = line.strip().split(",")
        if len(parts) == 3 and parts[0] != "t_ms":
            try:
                out.append(float(parts[2]))
            except ValueError:
                continue
    return out


def summary(folder: Path) -> dict[str, Any]:
    """What's recorded in a take: clips, sensor rows, labels."""
    labels: int | None = None
    try:
        data = json.loads((folder / "labels.json").read_text())
        labels = len(data) if isinstance(data, list) else None
    except (OSError, ValueError):
        pass
    return {
        "clips": clips(folder),
        "imu_rows": _count_rows(folder / "imu.csv"),
        "hr_rows": _count_rows(folder / "hr.csv"),
        "labels": labels,
        "has_protocol": (folder / "protocol.json").exists(),
    }
