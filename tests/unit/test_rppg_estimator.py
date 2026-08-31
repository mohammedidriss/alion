"""rPPG estimator + window source (ADR 008).

Feeds a synthetic RGB trace with a known embedded pulse and checks the
estimator recovers the rate, then that the source tags PulseSamples against a
window T_0 offset and marks them as PRV/rppg (not HRV).
"""

from __future__ import annotations

import math
from uuid import uuid4

from capture.rppg import RppgWindowSource, estimate_pulse
from capture.rppg.estimator import PulseWindow


def _synthetic_trace(
    bpm: float, fps: float, seconds: float, amp: float = 5.0
) -> list[tuple[float, float, float]]:
    """RGB trace with a clean pulse embedded in the green channel."""
    freq = bpm / 60.0
    n = int(fps * seconds)
    trace: list[tuple[float, float, float]] = []
    for i in range(n):
        t = i / fps
        g = 128.0 + amp * math.sin(2 * math.pi * freq * t)
        trace.append((128.0, g, 128.0))
    return trace


def test_recovers_known_pulse_rate() -> None:
    window = estimate_pulse(_synthetic_trace(bpm=72.0, fps=30.0, seconds=12.0), fps=30.0)
    assert 60.0 <= window.mean_bpm <= 84.0  # 72 ± tolerance
    assert window.quality > 0.5  # clean signal → most spectral power in-band
    assert len(window.beats_ms) == len(window.ibis_ms)  # aligned


def test_recovers_faster_pulse() -> None:
    window = estimate_pulse(_synthetic_trace(bpm=120.0, fps=30.0, seconds=12.0), fps=30.0)
    assert 108.0 <= window.mean_bpm <= 132.0  # 120 ± tolerance


def test_short_trace_returns_empty() -> None:
    # Under ~2 seconds of samples → not enough to resolve a pulse.
    window = estimate_pulse(_synthetic_trace(bpm=72.0, fps=30.0, seconds=1.0), fps=30.0)
    assert window == PulseWindow.empty()


def test_bad_fps_returns_empty() -> None:
    assert estimate_pulse(_synthetic_trace(72.0, 30.0, 12.0), fps=0.0) == PulseWindow.empty()


def test_window_source_tags_t0_and_marks_rppg() -> None:
    sid = uuid4()
    trace = _synthetic_trace(bpm=72.0, fps=30.0, seconds=12.0)
    start = 5000.0  # window began 5 s into the session (a T_0 offset)
    samples = list(RppgWindowSource(sid, trace, fps=30.0, window_start_ms=start))

    assert len(samples) > 3
    for s in samples:
        assert s.session_id == sid
        assert s.source == "rppg"  # a distinct cardiac source, not HRV
        assert s.t_ms >= start  # tagged against the window's T_0 offset
        assert 250.0 <= s.ibi_ms <= 2000.0
        assert math.isclose(s.pulse_bpm, 60_000.0 / s.ibi_ms, rel_tol=1e-9)
    # t_ms strictly increasing (beats in order)
    ts = [s.t_ms for s in samples]
    assert ts == sorted(ts)


def test_window_source_respects_min_quality() -> None:
    sid = uuid4()
    trace = _synthetic_trace(bpm=72.0, fps=30.0, seconds=12.0)
    # An impossibly high quality bar suppresses all output.
    samples = list(RppgWindowSource(sid, trace, fps=30.0, min_quality=1.01))
    assert samples == []
