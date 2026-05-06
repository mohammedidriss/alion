"""HRV capture sub-module.

Independent of `capture/cv` — depends only on `contracts` and `common`.
The replay driver works without hardware (CSV → HRSample stream); the
Polar BLE driver lands as a drop-in `polar.py` once the H10 arrives
(2026-05-16).
"""

from capture.hrv.replay import CsvReplaySource, parse_rr_csv

__all__ = ["CsvReplaySource", "parse_rr_csv"]
