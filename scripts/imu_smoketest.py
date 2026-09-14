#!/usr/bin/env python3
"""WT901BLECL BLE smoke test — validate the sensors before building the adapter.

This is the on-arrival check from docs/IMU_DUE_DILIGENCE.md: confirm the units
pair over BLE, stream data, decode correctly, and — the one unknown we said we'd
measure rather than trust — report the *actual sustained sample rate* on this Mac.

Usage:
  uv run python scripts/imu_smoketest.py scan [seconds]
  uv run python scripts/imu_smoketest.py measure <address> [seconds]

  scan    — discover BLE devices, highlight WitMotion "WT" units + addresses.
  measure — connect, subscribe to the data characteristic, decode the
            accel/gyro/angle stream, and report the sustained Hz + sample values.
"""

from __future__ import annotations

import asyncio
import struct
import sys
import time

from bleak import BleakClient, BleakScanner

# GATT layout — identical across the WT901BLE family (official SDK + community
# repos all agree). See docs/IMU_DUE_DILIGENCE.md.
NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"  # data stream (notify)
WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9a34fb"  # config/commands


def decode(buf: bytearray):
    """Parse complete WIT packets from buf. Returns (list_of_samples, leftover_bytes).

    The WT901BLECL BLE5.0 stream is a 20-byte 0x55/0x61 frame carrying
    accel(3) + angular-velocity(3) + angle(3) as nine little-endian int16.
    """
    out = []
    i, n = 0, len(buf)
    while n - i >= 20:
        if buf[i] != 0x55:
            i += 1  # resync to the next header
            continue
        flag = buf[i + 1]
        if flag == 0x61:
            ax, ay, az, wx, wy, wz, roll, pitch, yaw = struct.unpack(
                "<hhhhhhhhh", buf[i + 2 : i + 20]
            )
            out.append(
                {
                    "acc_g": (ax / 32768 * 16, ay / 32768 * 16, az / 32768 * 16),
                    "gyro_dps": (wx / 32768 * 2000, wy / 32768 * 2000, wz / 32768 * 2000),
                    "angle_deg": (roll / 32768 * 180, pitch / 32768 * 180, yaw / 32768 * 180),
                }
            )
            i += 20
        elif flag in (0x51, 0x52, 0x53, 0x71):
            i += 20  # other WIT frames (not used here) — skip a full frame
        else:
            i += 1
    return out, buf[i:]


async def scan(seconds: int = 8) -> None:
    print(f"Scanning {seconds}s for BLE devices (name + advertised service UUIDs)...")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    if not found:
        print("No BLE devices found at all — is Bluetooth on / permission granted?")
        return
    # Strongest signal first — the sensor on your desk should be near the top.
    items = sorted(
        found.values(), key=lambda da: da[1].rssi if da[1].rssi is not None else -999, reverse=True
    )
    wt = []
    print(f"  {'rssi':>4}  {'name':28}  service uuids / address")
    for dev, adv in items:
        name = adv.local_name or dev.name or "(no name)"
        svcs = [u.lower() for u in (adv.service_uuids or [])]
        # WitMotion units either advertise a "WT…" name or the ffe5 service (ffe4 = notify).
        is_wt = "WT" in name.upper() or any(("ffe5" in u or "ffe4" in u) for u in svcs)
        if is_wt:
            wt.append(dev)
        tail = ",".join(svcs) if svcs else dev.address
        mark = "  <-- WitMotion?" if is_wt else ""
        print(f"  {adv.rssi if adv.rssi is not None else 0:>4}  {name:28.28}  {tail}{mark}")
    print()
    if wt:
        print(f"Found {len(wt)} likely WitMotion unit(s). Measure the rate with:")
        for d in wt:
            print(f"  .venv/bin/python scripts/imu_smoketest.py measure {d.address} 15")
    else:
        print("Still no WitMotion unit. Most likely it's OFF, dead, or already connected")
        print("to a phone/app (a connected BLE peripheral stops advertising). See the checklist.")


async def measure(address: str, seconds: int = 15) -> None:
    buf = bytearray()
    count = {"data": 0}
    samples: list = []
    t0: float | None = None

    def cb(_sender, data: bytearray) -> None:
        nonlocal t0
        if t0 is None:
            t0 = time.monotonic()
        buf.extend(data)
        decoded, leftover = decode(buf)
        buf[:] = leftover
        for s in decoded:
            count["data"] += 1
            if len(samples) < 5:
                samples.append(s)

    print(f"Connecting to {address} ...")
    async with BleakClient(address, timeout=20) as c:
        print(f"Connected: {c.is_connected}. Streaming for {seconds}s ...")
        await c.start_notify(NOTIFY_UUID, cb)
        await asyncio.sleep(seconds)
        await c.stop_notify(NOTIFY_UUID)

    dur = (time.monotonic() - t0) if t0 else 0.0
    print(f"\ndata packets: {count['data']}")
    if dur > 0:
        print(f"MEASURED SUSTAINED RATE: {count['data'] / dur:.1f} Hz over {dur:.1f}s")
    else:
        print("No data packets decoded — check the notify UUID / that the unit is streaming.")
    print("\nfirst decoded samples:")
    for s in samples:
        print("  " + str({k: tuple(round(x, 2) for x in v) for k, v in s.items()}))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if mode == "scan":
        asyncio.run(scan(int(sys.argv[2]) if len(sys.argv) > 2 else 8))
    elif mode == "measure" and len(sys.argv) > 2:
        asyncio.run(measure(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 15))
    else:
        print(__doc__)
