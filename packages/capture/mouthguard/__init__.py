"""Instrumented-mouthguard head-impact capture adapter (ADR 007).

Independent capture adapter: depends only on `contracts` + `common`, imports no
sibling capture module. Produces `HeadImpactEvent`s — a received head event,
distinct from a thrown punch, never merged into `punch_event`/`imu_sample`.
Advisory telemetry only, not a concussion diagnosis.
"""

from capture.mouthguard.device import (
    ImpactDecoder,
    MouthguardBleSource,
    impact_event_from_reading,
    scan_for_impact_devices,
)
from capture.mouthguard.replay import (
    CsvImpactReplaySource,
    ImpactReading,
    parse_impacts_csv,
)

__all__ = [
    "CsvImpactReplaySource",
    "ImpactDecoder",
    "ImpactReading",
    "MouthguardBleSource",
    "impact_event_from_reading",
    "parse_impacts_csv",
    "scan_for_impact_devices",
]
