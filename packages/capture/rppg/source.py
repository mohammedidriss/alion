"""rPPG window source — turns an RGB trace into `PulseSample`s (ADR 008).

A between-rounds, low-motion fallback for the Polar H10. Per Decision 2A this
adapter does its own frame/ROI handling and does NOT import `capture.cv`.

T_0 tagging: each emitted `PulseSample.t_ms` is
`window_start_ms + beat_offset_within_window`, where `window_start_ms` is the
SessionClock offset of the window's first frame — supplied by the composition
root via `clock.now_offset_ms()` (live) or `frame_index * 1000/fps` (offline).
The estimator works in window-relative time; only this layer knows T_0.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

from capture.rppg.estimator import RgbTrace, estimate_pulse
from contracts import PulseSample


def center_roi_mean_rgb(frame: Any, roi_fraction: float = 0.5) -> tuple[float, float, float]:
    """Mean (R, G, B) of a centred ROI of a BGR frame (OpenCV order in → RGB out).

    A deliberately simple skin-region proxy — a proper face detector is a
    follow-up; kept dependency-light and independent of `capture.cv`.
    """
    import numpy as np

    arr = np.asarray(frame)
    h, w = arr.shape[0], arr.shape[1]
    fh, fw = int(h * roi_fraction), int(w * roi_fraction)
    y0, x0 = (h - fh) // 2, (w - fw) // 2
    roi = arr[y0 : y0 + fh, x0 : x0 + fw]
    b, g, r = (float(roi[:, :, i].mean()) for i in range(3))
    return r, g, b


class RppgWindowSource:
    """Iterable that yields `PulseSample`s from one low-motion window's RGB trace.

    Emits one sample per inter-beat interval, carried on the *later* beat of the
    pair (as `HRSample` carries the RR to its previous beat). Windows below
    `min_quality` yield nothing.
    """

    def __init__(
        self,
        session_id: UUID,
        rgb_trace: RgbTrace,
        fps: float,
        *,
        window_start_ms: float = 0.0,
        min_quality: float = 0.0,
    ) -> None:
        self.session_id = session_id
        self.rgb_trace = rgb_trace
        self.fps = fps
        self.window_start_ms = window_start_ms
        self.min_quality = min_quality

    def __iter__(self) -> Iterator[PulseSample]:
        window = estimate_pulse(self.rgb_trace, self.fps)
        if not window.ibis_ms or window.quality < self.min_quality:
            return
        # beats_ms and ibis_ms are aligned: beats_ms[i] closes interval ibis_ms[i].
        for beat_time, ibi in zip(window.beats_ms, window.ibis_ms, strict=True):
            yield PulseSample(
                session_id=self.session_id,
                t_ms=self.window_start_ms + beat_time,
                ibi_ms=ibi,
                pulse_bpm=60_000.0 / ibi,
                quality=window.quality,
                source="rppg",
            )
