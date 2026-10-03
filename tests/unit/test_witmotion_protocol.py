"""WitMotion WT901BLECL wire protocol — byte-exact commands and decoding, no hardware.

These frames were confirmed against the real units on 2026-10-03 (register reads
returned 10 Hz / 20 Hz / 4.21 V factory values; writes to 100 Hz / 42 Hz read back
as saved), so the tests pin that known-good protocol against regressions.
"""

from __future__ import annotations

import struct

import pytest

from capture.imu import witmotion as wm


def _data_frame(ax: int, ay: int, az: int, wx: int = 0, wy: int = 0, wz: int = 0) -> bytes:
    return bytes([0x55, 0x61]) + struct.pack("<9h", ax, ay, az, wx, wy, wz, 0, 0, 0)


def _register_frame(start: int, *values: int) -> bytes:
    vals = list(values) + [0] * (8 - len(values))
    return bytes([0x55, 0x71]) + struct.pack("<9H", start, *vals)


# --- command frames ---------------------------------------------------------


def test_unlock_and_save_frames() -> None:
    assert wm.cmd_unlock() == bytes.fromhex("ffaa6988b5")
    assert wm.cmd_save() == bytes.fromhex("ffaa000000")
    assert wm.cmd_factory_reset() == bytes.fromhex("ffaa000100")


@pytest.mark.parametrize(
    ("hz", "frame"),
    [(10, "ffaa030600"), (50, "ffaa030800"), (100, "ffaa030900"), (200, "ffaa030b00")],
)
def test_set_rate_frames(hz: float, frame: str) -> None:
    assert wm.cmd_set_rate(hz) == bytes.fromhex(frame)


def test_set_rate_rejects_unsupported() -> None:
    with pytest.raises(ValueError):
        wm.cmd_set_rate(37)


@pytest.mark.parametrize(
    ("hz", "frame"), [(20, "ffaa1f0400"), (42, "ffaa1f0300"), (98, "ffaa1f0200")]
)
def test_set_bandwidth_frames(hz: int, frame: str) -> None:
    assert wm.cmd_set_bandwidth(hz) == bytes.fromhex(frame)


def test_set_bandwidth_rejects_unsupported() -> None:
    with pytest.raises(ValueError):
        wm.cmd_set_bandwidth(50)


def test_calibrate_and_read_frames() -> None:
    assert wm.cmd_calibrate_accel(True) == bytes.fromhex("ffaa010100")
    assert wm.cmd_calibrate_accel(False) == bytes.fromhex("ffaa010000")
    assert wm.cmd_read_register(wm.REG_RRATE) == bytes.fromhex("ffaa270300")


def test_code_reverse_lookups() -> None:
    assert wm.rate_hz(0x09) == 100
    assert wm.bandwidth_hz(0x03) == 42
    assert wm.rate_hz(0x7F) is None


# --- decoding ---------------------------------------------------------------


def test_decode_data_frame_scaling() -> None:
    # 2048 / 32768 * 16 g = 1 g  (unit lying flat); 16384 / 32768 * 2000 = 1000 °/s
    samples, replies, rest = wm.decode(_data_frame(0, 0, 2048, wz=16384))
    assert len(samples) == 1 and not replies and rest == b""
    assert samples[0].acc_g == pytest.approx((0.0, 0.0, 1.0))
    assert samples[0].gyro_dps[2] == pytest.approx(1000.0)


def test_decode_register_reply() -> None:
    samples, replies, _ = wm.decode(_register_frame(wm.REG_RRATE, 0x09, 0x01))
    assert not samples and len(replies) == 1
    assert replies[0].get(wm.REG_RRATE) == 0x09
    assert replies[0].get(wm.REG_RRATE + 1) == 0x01
    assert replies[0].get(wm.REG_RRATE + 8) is None  # outside the 8-register block


def test_decode_resyncs_and_keeps_partial_tail() -> None:
    frame = _data_frame(0, 0, 2048)
    buf = b"\x00\x12\x99" + frame + _register_frame(wm.REG_VOLTAGE, 421) + frame[:7]
    samples, replies, rest = wm.decode(buf)
    assert len(samples) == 1 and len(replies) == 1
    assert rest == frame[:7]  # incomplete frame carried to the next notification
    # feeding the tail plus the remainder completes it
    samples2, _, rest2 = wm.decode(rest + frame[7:])
    assert len(samples2) == 1 and rest2 == b""


def test_decode_skips_legacy_frames() -> None:
    legacy = bytes([0x55, 0x51]) + bytes(18)
    samples, replies, rest = wm.decode(legacy + _data_frame(0, 0, 2048))
    assert len(samples) == 1 and not replies and rest == b""


# --- battery ----------------------------------------------------------------


def test_voltage_units() -> None:
    assert wm.voltage_volts(421) == pytest.approx(4.21)  # 0.01 V units (observed)
    assert wm.voltage_volts(4210) == pytest.approx(4.21)  # millivolt variant


def test_battery_percent_bounds_and_monotonic() -> None:
    assert wm.battery_percent(4.21) == 100
    assert wm.battery_percent(3.2) == 0
    levels = [wm.battery_percent(v / 100) for v in range(330, 421, 5)]
    assert levels == sorted(levels)
