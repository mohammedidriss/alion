"""Second-pass (offline) punch detectors.

The capture pipeline saves a per-frame keypoint parquet at session end.
Second-pass detectors run *after* capture and re-examine that parquet
with slower / heavier algorithms than the live `HeuristicPunchDetector`.
Their output is reconciled with the live events to produce a consensus
list that downstream consumers (rounds_export, advice LLM, dashboard
counter) prefer when present.

Concrete adapters:
  - `StricterHeuristicSecondPass` — same heuristic, tighter thresholds.
    Used as the default placeholder until a learned model is plugged in.
  - `LSTMSecondPass` — wraps a trained pose-sequence classifier (lives
    in `data/ml/punch_lstm_v1.pkl`). Auto-loads when the file exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from analyze.punch_detector_heuristic import HeuristicPunchDetector
from contracts import PoseFrame, PunchEvent


class SecondPassDetector(ABC):
    """Stateless adapter — fed the full saved pose stream, returns events.

    Implementations must be deterministic (same input → same output) so
    the reconciler can be exercised in tests without flake.
    """

    name: str = "abstract"

    @abstractmethod
    def detect(
        self, frames: Iterable[PoseFrame], *, stance: str | None = None
    ) -> list[PunchEvent]: ...


class StricterHeuristicSecondPass(SecondPassDetector):
    """Same heuristic as live, but with the original strict thresholds.

    Live runs with relaxed gates (so it doesn't drop too many real
    punches mid-session). Offline can afford to be picky — it only runs
    once at session end. When live + strict-offline both fire on the
    same event, that's a high-confidence consensus event.
    """

    name = "stricter_heuristic"

    def __init__(
        self,
        *,
        min_elbow_angle_deg: float = 90.0,
        min_extension_ratio: float = 1.20,
        chambered_max_deg: float = 100.0,
        extended_min_deg: float = 155.0,
    ) -> None:
        self._min_elbow_angle_deg = min_elbow_angle_deg
        self._min_extension_ratio = min_extension_ratio
        self._chambered_max_deg = chambered_max_deg
        self._extended_min_deg = extended_min_deg

    def detect(self, frames: Iterable[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
        det = HeuristicPunchDetector(
            stance=stance,
            min_elbow_angle_deg=self._min_elbow_angle_deg,
            min_extension_ratio=self._min_extension_ratio,
            chambered_max_deg=self._chambered_max_deg,
            extended_min_deg=self._extended_min_deg,
        )
        out: list[PunchEvent] = []
        for f in frames:
            out.extend(det.feed(f))
        return out


def default_second_pass() -> SecondPassDetector:
    """Pick the best available second-pass detector at runtime.

    Tries LSTM (if the model file exists on disk) first, falls back to
    the stricter heuristic. Centralised so tests + the route both use
    the same selection logic.
    """
    try:
        from analyze.lstm_second_pass import LSTMSecondPass

        det = LSTMSecondPass.try_load()
        if det is not None:
            return det
    except Exception:
        pass
    return StricterHeuristicSecondPass()
