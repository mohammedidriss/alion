"""HRV capture sub-module.

Independent of `capture/cv` — depends only on `contracts` and `common`.
The replay driver works without hardware (CSV → HRSample stream); the
Polar BLE driver streams live RR intervals over Bluetooth LE.
"""

from capture.hrv.replay import CsvReplaySource, parse_rr_csv

__all__ = ["CsvReplaySource", "parse_rr_csv"]
