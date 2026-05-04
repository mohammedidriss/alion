"""Parquet writer for PoseFrame batches.

Layout: one row per frame, columns flattened —
  session_id, frame_index, t_ms, lm00_x, lm00_y, lm00_z, lm00_v, ..., lm32_v
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame

if TYPE_CHECKING:
    import pyarrow as pa


_LM_COLS = [f"lm{i:02d}_{c}" for i in range(NUM_POSE_LANDMARKS) for c in ("x", "y", "z", "v")]
_BASE_COLS = ["session_id", "frame_index", "t_ms"]
ALL_COLS = _BASE_COLS + _LM_COLS


def _flatten(frame: PoseFrame) -> list[Any]:
    out: list[Any] = [str(frame.session_id), frame.frame_index, frame.t_ms]
    for lm in frame.landmarks:
        out.extend([lm.x, lm.y, lm.z, lm.visibility])
    return out


class PoseParquetWriter:
    """Buffers frames in memory then writes one parquet file on close.

    For Phase 1 sessions are short (≤6 minutes ≈ 10800 frames @30fps); buffering
    the whole session is fine. Phase 8 may move to chunked writes.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._rows: list[list[Any]] = []

    def append(self, frame: PoseFrame) -> None:
        self._rows.append(_flatten(frame))

    def __len__(self) -> int:
        return len(self._rows)

    def close(self) -> Path:
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._rows:
            # Write an empty table with the right schema so readers don't crash.
            arrays: list[pa.Array] = [pa.array([]) for _ in ALL_COLS]
            table = pa.table(dict(zip(ALL_COLS, arrays, strict=True)))
        else:
            cols: dict[str, list[Any]] = {c: [] for c in ALL_COLS}
            for row in self._rows:
                for col, val in zip(ALL_COLS, row, strict=True):
                    cols[col].append(val)
            table = pa.table(cols)
        pq.write_table(table, self.path)  # type: ignore[no-untyped-call]
        return self.path


def read_pose_parquet(path: str | Path) -> list[PoseFrame]:
    """Read a parquet file back into PoseFrame instances. Used by tests + replay."""
    import pyarrow.parquet as pq

    table = pq.read_table(Path(path))  # type: ignore[no-untyped-call]
    if table.num_rows == 0:
        return []
    rows: Sequence[dict[str, Any]] = table.to_pylist()
    out: list[PoseFrame] = []
    for r in rows:
        landmarks = tuple(
            Landmark(
                x=r[f"lm{i:02d}_x"],
                y=r[f"lm{i:02d}_y"],
                z=r[f"lm{i:02d}_z"],
                visibility=r[f"lm{i:02d}_v"],
            )
            for i in range(NUM_POSE_LANDMARKS)
        )
        out.append(
            PoseFrame(
                session_id=UUID(r["session_id"]),
                frame_index=int(r["frame_index"]),
                t_ms=float(r["t_ms"]),
                landmarks=landmarks,
            )
        )
    return out


def write_pose_parquet(path: str | Path, frames: Iterable[PoseFrame]) -> Path:
    """Convenience: write an iterable of frames in one call."""
    w = PoseParquetWriter(path)
    for f in frames:
        w.append(f)
    return w.close()
