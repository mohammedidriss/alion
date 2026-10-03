"""IMU capture sub-module — WitMotion WT901BLECL wrist sensors.

Independent of `capture/cv` and `capture/hrv` — depends only on `contracts` and
`common`. Exports only the pure wire protocol, so importing this package never
touches Bluetooth; BLE transport lives in the callers (`scripts/imu_tool.py`,
and the live `WT901Source` adapter).
"""

from capture.imu.witmotion import (
    NOTIFY_UUID,
    WRITE_UUID,
    ImuSample,
    RegisterReply,
    decode,
)

__all__ = ["NOTIFY_UUID", "WRITE_UUID", "ImuSample", "RegisterReply", "decode"]
