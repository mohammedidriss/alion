"""LSTM-based second-pass detector.

Wraps the model trained by `scripts/ml/train_punch_lstm.py`. At runtime,
`default_second_pass()` calls `LSTMSecondPass.try_load()` and uses the
LSTM if `data/ml/punch_lstm_v1.pkl` exists; otherwise it falls back to
the heuristic.

Sliding-window inference: take the same `WINDOW_FRAMES` × 264-feature
windows the trainer used, score each window, and emit a punch event
whenever the model crosses a confidence threshold AND the window
hasn't fired in the last `refractory_ms`. The event timestamp is the
center of the window, the hand is inferred from which wrist had the
larger displacement during the window.
"""

from __future__ import annotations

import math
import pickle
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from analyze.second_pass import SecondPassDetector
from contracts import Hand, LeadOrRear, PoseFrame, PunchEvent

DEFAULT_MODEL_PATH = Path("data/ml/punch_lstm_v1.pkl")
# Conservative threshold — at 0.65 the v1 LSTM fired ~39 false
# positives on a no-movement session because the model was trained on
# Olympic Boxing footage and doesn't generalise to other camera angles.
# 0.85 means only the most confident windows fire; we keep recall low
# in exchange for far higher precision until in-domain labels are
# available for retraining.
DEFAULT_CONFIDENCE = 0.85
DEFAULT_REFRACTORY_MS = 200.0


class LSTMSecondPass(SecondPassDetector):
    name = "lstm_v1"

    def __init__(
        self,
        *,
        weights: dict[str, Any],
        model_path: Path,
        confidence_threshold: float = DEFAULT_CONFIDENCE,
        refractory_ms: float = DEFAULT_REFRACTORY_MS,
    ) -> None:
        self._weights = weights
        self._model_path = model_path
        self._threshold = confidence_threshold
        self._refractory_ms = refractory_ms

    @classmethod
    def try_load(cls, model_path: Path = DEFAULT_MODEL_PATH) -> LSTMSecondPass | None:
        if not model_path.exists():
            return None
        try:
            with model_path.open("rb") as f:
                weights = pickle.load(f)
        except Exception:
            return None
        if "state_dict" not in weights or "feat_dim" not in weights:
            return None
        return cls(weights=weights, model_path=model_path)

    def detect(self, frames: Iterable[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
        try:
            import numpy as np
            import torch
            from torch import nn
        except ImportError:
            # PyTorch missing — degrade to nothing, the route falls back.
            return []

        frames_list = list(frames)
        if not frames_list:
            return []

        T = int(self._weights["window_frames"])
        F = int(self._weights["feat_dim"])
        hidden = int(self._weights.get("hidden", 128))
        labels = list(self._weights["labels"])
        mean = np.asarray(self._weights["mean"], dtype=np.float32)
        std = np.asarray(self._weights["std"], dtype=np.float32) + 1e-6

        # Re-create the same architecture the trainer used.
        class PunchLSTM(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.lstm = nn.LSTM(F, hidden, num_layers=1, batch_first=True)
                self.head = nn.Linear(hidden, len(labels))

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                out, _ = self.lstm(x)
                return cast(torch.Tensor, self.head(out.mean(dim=1)))

        model = PunchLSTM()
        # Load numpy state_dict back into torch tensors.
        state = {k: torch.from_numpy(np.asarray(v)) for k, v in self._weights["state_dict"].items()}
        model.load_state_dict(state)
        model.eval()
        punch_idx = labels.index("punch") if "punch" in labels else 1

        # Build the per-frame feature vector (33 lm × 4 + 33 wl × 4 = 264).
        def _frame_features(f: PoseFrame) -> list[float]:
            row: list[float] = []
            for lm in f.landmarks:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])
            if f.world_landmarks is not None:
                for wl in f.world_landmarks:
                    row.extend([wl.x, wl.y, wl.z, wl.visibility])
            else:
                row.extend([0.0] * (33 * 4))
            return row

        feature_seq = [_frame_features(f) for f in frames_list]
        if any(len(r) != F for r in feature_seq):
            # Schema drift between trainer and runtime.
            return []
        feature_arr = np.asarray(feature_seq, dtype=np.float32)

        # Slide windows; stride must be small enough to localise punch
        # to within ~refractory_ms.
        stride = max(1, int(0.1 * T))  # 10% of window
        events: list[PunchEvent] = []
        last_event_t: float | None = None
        with torch.no_grad():
            for start in range(0, len(frames_list) - T + 1, stride):
                window = feature_arr[start : start + T]
                window_n = (window - mean) / std
                logits = model(torch.from_numpy(window_n).unsqueeze(0))
                probs = torch.softmax(logits[0], dim=0).cpu().numpy()
                if probs[punch_idx] < self._threshold:
                    continue
                center_idx = start + T // 2
                center_frame = frames_list[center_idx]
                t_ms = float(center_frame.t_ms)
                if last_event_t is not None and (t_ms - last_event_t) < self._refractory_ms:
                    continue
                last_event_t = t_ms
                hand = _infer_hand(frames_list[start : start + T])
                events.append(
                    PunchEvent(
                        session_id=center_frame.session_id,
                        t_ms=t_ms,
                        hand=cast(Hand, hand),
                        lead_or_rear=cast("LeadOrRear | None", _lead_or_rear(hand, stance)),
                        velocity_ms=_window_peak_speed(frames_list[start : start + T], hand),
                        velocity_source="world"
                        if center_frame.world_landmarks is not None
                        else "image_heuristic",
                        detected_by="lstm_v1",
                        confidence=float(probs[punch_idx]),
                    )
                )
        return events


def _xyz(frame: PoseFrame, idx: int, *, use_world: bool) -> tuple[float, float, float]:
    """Return (x, y, z) for a landmark, preferring world coords when present."""
    if use_world and frame.world_landmarks is not None:
        wl = frame.world_landmarks[idx]
        return (wl.x, wl.y, wl.z)
    lm = frame.landmarks[idx]
    return (lm.x, lm.y, lm.z)


def _infer_hand(window: list[PoseFrame]) -> str:
    """Hand inference: whichever wrist travelled further during the window."""
    if len(window) < 2:
        return "right"
    use_world = window[0].world_landmarks is not None
    l_total = r_total = 0.0
    for i in range(1, len(window)):
        la = _xyz(window[i - 1], 15, use_world=use_world)
        lb = _xyz(window[i], 15, use_world=use_world)
        ra = _xyz(window[i - 1], 16, use_world=use_world)
        rb = _xyz(window[i], 16, use_world=use_world)
        l_total += math.hypot(lb[0] - la[0], lb[1] - la[1], lb[2] - la[2])
        r_total += math.hypot(rb[0] - ra[0], rb[1] - ra[1], rb[2] - ra[2])
    return "right" if r_total >= l_total else "left"


def _window_peak_speed(window: list[PoseFrame], hand: str) -> float:
    """Crude peak speed over the window for the punching wrist (m/s
    when world landmarks present, normalised otherwise)."""
    idx = 15 if hand == "left" else 16
    use_world = all(f.world_landmarks is not None for f in window)
    peak = 0.0
    for i in range(1, len(window)):
        a, b = window[i - 1], window[i]
        dt = max(1e-3, (b.t_ms - a.t_ms) / 1000.0)
        la = _xyz(a, idx, use_world=use_world)
        lb = _xyz(b, idx, use_world=use_world)
        d = math.hypot(lb[0] - la[0], lb[1] - la[1], lb[2] - la[2])
        peak = max(peak, d / dt)
    return round(peak, 2)


def _lead_or_rear(hand: str, stance: str | None) -> str | None:
    if stance == "orthodox":
        return "lead" if hand == "left" else "rear"
    if stance == "southpaw":
        return "lead" if hand == "right" else "rear"
    return None


__all__ = ["LSTMSecondPass"]
