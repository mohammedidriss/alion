"""WitMotion WT901BLECL (BLE 5.0) wire protocol — pure bytes, no Bluetooth.

Everything needed to talk to the sensor: the GATT characteristic UUIDs, the
command frames that configure it (unlock → write register → save; read
register), and the decoder for what it streams back (data frames + register
replies). Deliberately free of `bleak` so it is unit-testable without hardware;
the BLE transport lives in the callers — `scripts/imu_tool.py` (configuration)
now, and the live `WT901Source` capture adapter next.

Source: docs/IMU_DUE_DILIGENCE.md and WitMotion's official SDK
(WITMOTION/WitBluetooth_BWT901BLE5_0). All multi-byte fields are little-endian.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from itertools import pairwise

NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"  # data frames + register replies
WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9a34fb"  # command frames

# Register map (WitMotion standard).
REG_SAVE = 0x00  # 0x0000 = save config, 0x0001 = restore factory defaults
REG_CALSW = 0x01  # calibration mode: 0x0000 normal, 0x0001 accelerometer calibration
REG_RRATE = 0x03  # output ("return") rate — see RATE_CODES
REG_BANDWIDTH = 0x1F  # digital low-pass filter bandwidth — see BANDWIDTH_CODES
REG_VOLTAGE = 0x64  # battery voltage

# Output rate (Hz) → RRATE code. The factory default is 10 Hz: only 1–2 samples
# across a 100–150 ms punch. We run at 100 Hz (50 Hz if BLE can't sustain it).
RATE_CODES: dict[float, int] = {
    0.2: 0x01,
    0.5: 0x02,
    1: 0x03,
    2: 0x04,
    5: 0x05,
    10: 0x06,
    20: 0x07,
    50: 0x08,
    100: 0x09,
    200: 0x0B,
}

# Low-pass bandwidth (Hz) → BANDWIDTH code. A narrow filter smears the sharp
# acceleration spike of a punch; ≥98 Hz preserves it.
BANDWIDTH_CODES: dict[int, int] = {
    256: 0x00,
    188: 0x01,
    98: 0x02,
    42: 0x03,
    20: 0x04,
    10: 0x05,
    5: 0x06,
}

ACC_RANGE_G = 16.0
GYRO_RANGE_DPS = 2000.0
ANGLE_RANGE_DEG = 180.0

_FRAME_LEN = 20
_HEADER = 0x55
_FLAG_DATA = 0x61  # accel + gyro + angle in one frame (the BLE 5.0 default)
_FLAG_REGISTER = 0x71  # reply to a register read
_FLAGS_SKIP = (0x51, 0x52, 0x53)  # legacy single-quantity frames — skip whole


def _frame(reg: int, value: int) -> bytes:
    """5-byte write frame: FF AA <reg> <value lo> <value hi>."""
    return bytes([0xFF, 0xAA, reg & 0xFF, value & 0xFF, (value >> 8) & 0xFF])


def cmd_unlock() -> bytes:
    """Unlock configuration writes. Send before each write — it opens a short window."""
    return bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5])


def cmd_save() -> bytes:
    """Persist the current configuration across power cycles."""
    return _frame(REG_SAVE, 0x0000)


def cmd_factory_reset() -> bytes:
    """Restore factory defaults — the recovery path if a unit gets misconfigured."""
    return _frame(REG_SAVE, 0x0001)


def cmd_set_rate(hz: float) -> bytes:
    if hz not in RATE_CODES:
        raise ValueError(f"unsupported rate {hz} Hz; choose from {sorted(RATE_CODES)}")
    return _frame(REG_RRATE, RATE_CODES[hz])


def cmd_set_bandwidth(hz: int) -> bytes:
    if hz not in BANDWIDTH_CODES:
        raise ValueError(f"unsupported bandwidth {hz} Hz; choose from {sorted(BANDWIDTH_CODES)}")
    return _frame(REG_BANDWIDTH, BANDWIDTH_CODES[hz])


def cmd_calibrate_accel(on: bool) -> bytes:
    """Enter (on) / leave (off) accelerometer calibration. The unit must be flat and still."""
    return _frame(REG_CALSW, 0x0001 if on else 0x0000)


def cmd_read_register(reg: int) -> bytes:
    """Request register `reg`; the unit answers with a 0x71 frame of 8 registers from `reg`."""
    return bytes([0xFF, 0xAA, 0x27, reg & 0xFF, 0x00])


def rate_hz(code: int) -> float | None:
    """RRATE code → Hz (None if the code isn't a known rate)."""
    return {v: k for k, v in RATE_CODES.items()}.get(code)


def bandwidth_hz(code: int) -> int | None:
    """BANDWIDTH code → Hz (None if the code isn't a known bandwidth)."""
    return {v: k for k, v in BANDWIDTH_CODES.items()}.get(code)


@dataclass(frozen=True)
class ImuSample:
    acc_g: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]
    angle_deg: tuple[float, float, float]


@dataclass(frozen=True)
class RegisterReply:
    """Eight consecutive 16-bit registers, starting at `start_reg`."""

    start_reg: int
    values: tuple[int, ...]

    def get(self, reg: int) -> int | None:
        i = reg - self.start_reg
        return self.values[i] if 0 <= i < len(self.values) else None


def _scale(raw: int, full_scale: float) -> float:
    return raw / 32768.0 * full_scale


def decode(buf: bytes) -> tuple[list[ImuSample], list[RegisterReply], bytes]:
    """Parse every complete frame in `buf` → (samples, register replies, leftover).

    Resyncs on the 0x55 header, so garbage or connecting mid-stream is harmless.
    The leftover is an incomplete tail to prepend to the next notification.
    """
    samples: list[ImuSample] = []
    replies: list[RegisterReply] = []
    i, n = 0, len(buf)
    while n - i >= _FRAME_LEN:
        if buf[i] != _HEADER:
            i += 1
            continue
        flag = buf[i + 1]
        body = buf[i + 2 : i + _FRAME_LEN]
        if flag == _FLAG_DATA:
            ax, ay, az, wx, wy, wz, roll, pitch, yaw = struct.unpack("<9h", body)
            samples.append(
                ImuSample(
                    acc_g=(
                        _scale(ax, ACC_RANGE_G),
                        _scale(ay, ACC_RANGE_G),
                        _scale(az, ACC_RANGE_G),
                    ),
                    gyro_dps=(
                        _scale(wx, GYRO_RANGE_DPS),
                        _scale(wy, GYRO_RANGE_DPS),
                        _scale(wz, GYRO_RANGE_DPS),
                    ),
                    angle_deg=(
                        _scale(roll, ANGLE_RANGE_DEG),
                        _scale(pitch, ANGLE_RANGE_DEG),
                        _scale(yaw, ANGLE_RANGE_DEG),
                    ),
                )
            )
            i += _FRAME_LEN
        elif flag == _FLAG_REGISTER:
            start, *vals = struct.unpack("<9H", body)
            replies.append(RegisterReply(start_reg=start, values=tuple(vals)))
            i += _FRAME_LEN
        elif flag in _FLAGS_SKIP:
            i += _FRAME_LEN
        else:
            i += 1  # not a frame we know — resync on the next header
    return samples, replies, bytes(buf[i:])


def voltage_volts(raw: int) -> float:
    """Voltage register → volts. Firmware reports 0.01 V units (412 = 4.12 V); also
    accept millivolts (4120) so a firmware variant can't silently mislead us."""
    return raw / 1000.0 if raw >= 1000 else raw / 100.0


# Single-cell LiPo: ~4.2 V full, ~3.3 V empty. Piecewise-linear, approximate.
_LIPO_CURVE: tuple[tuple[float, int], ...] = (
    (3.30, 0),
    (3.50, 5),
    (3.65, 20),
    (3.75, 40),
    (3.85, 60),
    (4.00, 80),
    (4.15, 100),
)


def battery_percent(volts: float) -> int:
    """Approximate state of charge from cell voltage (0–100)."""
    if volts <= _LIPO_CURVE[0][0]:
        return 0
    if volts >= _LIPO_CURVE[-1][0]:
        return 100
    for (v0, p0), (v1, p1) in pairwise(_LIPO_CURVE):
        if v0 <= volts <= v1:
            return round(p0 + (p1 - p0) * (volts - v0) / (v1 - v0))
    return 0
