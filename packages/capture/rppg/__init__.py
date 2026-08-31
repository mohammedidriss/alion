"""rPPG cardiac-fallback capture adapter (ADR 008).

Independent capture adapter: depends only on `contracts` + `common`, imports no
sibling capture module (notably not `capture.cv`, per Decision 2A). Produces
`PulseSample`s — pulse-rate variability (PRV) from ordinary video, a
between-rounds low-motion *fallback* for the Polar H10. A distinct cardiac
source, never merged into the HRV (`hr_sample`) stream and not equivalent to it.
Advisory only.
"""

from capture.rppg.estimator import PulseWindow, RgbTrace, estimate_pulse
from capture.rppg.source import RppgWindowSource, center_roi_mean_rgb

__all__ = [
    "PulseWindow",
    "RgbTrace",
    "RppgWindowSource",
    "center_roi_mean_rgb",
    "estimate_pulse",
]
