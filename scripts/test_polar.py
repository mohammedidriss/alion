#!/usr/bin/env python3
"""Quick Polar H10 BLE test — scan, connect, stream HR + RR intervals.

Usage:
    # Wet the strap electrodes, put it on, then:
    uv run python scripts/test_polar.py

    # If multiple BLE HR devices nearby, pass a name fragment:
    uv run python scripts/test_polar.py --name "Polar H10"

Press Ctrl-C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys
import time

# Bluetooth SIG Heart Rate Service UUIDs
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_hr_measurement(data: bytearray) -> dict:
    """Parse a Heart Rate Measurement characteristic value (BLE spec §3.105).

    Returns dict with keys:
      hr_bpm    — instantaneous heart rate
      rr_ms     — list of RR intervals in milliseconds (may be empty)
      contact   — True/False/None (sensor contact status, if reported)
      energy_kj — cumulative energy in kJ, if present
    """
    flags = data[0]
    hr_16bit = bool(flags & 0x01)
    contact_supported = bool(flags & 0x04)
    contact_detected = bool(flags & 0x02) if contact_supported else None
    energy_present = bool(flags & 0x08)
    rr_present = bool(flags & 0x10)

    offset = 1
    if hr_16bit:
        hr_bpm = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    else:
        hr_bpm = data[offset]
        offset += 1

    energy_kj = None
    if energy_present:
        energy_kj = struct.unpack_from("<H", data, offset)[0]
        offset += 2

    rr_intervals: list[float] = []
    if rr_present:
        while offset + 1 < len(data):
            raw = struct.unpack_from("<H", data, offset)[0]
            rr_intervals.append(raw * 1000.0 / 1024.0)  # convert to ms
            offset += 2

    return {
        "hr_bpm": hr_bpm,
        "rr_ms": rr_intervals,
        "contact": contact_detected,
        "energy_kj": energy_kj,
    }


async def scan_for_hr(name_filter: str | None, timeout: float = 10.0):
    """Scan for BLE devices advertising the Heart Rate service."""
    from bleak import BleakScanner

    print(f"Scanning for Heart Rate devices ({timeout}s)...")
    devices = await BleakScanner.discover(
        timeout=timeout,
        service_uuids=[HR_SERVICE_UUID],
    )
    if name_filter:
        devices = [d for d in devices if name_filter.lower() in (d.name or "").lower()]
    return devices


async def stream_hr(address: str):
    """Connect to the device and stream HR + RR data until Ctrl-C."""
    from bleak import BleakClient

    sample_count = 0
    rr_total = 0
    t0 = time.monotonic()

    def on_hr_data(_sender, data: bytearray):
        nonlocal sample_count, rr_total
        parsed = parse_hr_measurement(data)
        elapsed = time.monotonic() - t0
        hr = parsed["hr_bpm"]
        rrs = parsed["rr_ms"]
        contact = parsed["contact"]
        rr_total += len(rrs)

        contact_str = "✓" if contact else ("✗ NO CONTACT" if contact is False else "?")
        rr_str = ", ".join(f"{r:.0f}" for r in rrs) if rrs else "—"
        sample_count += 1

        print(
            f"  [{elapsed:6.1f}s]  HR {hr:3d} bpm  |  "
            f"RR [{rr_str}] ms  |  contact: {contact_str}  |  "
            f"samples: {sample_count}  rr_total: {rr_total}"
        )

    print(f"\nConnecting to {address}...")
    async with BleakClient(address) as client:
        print(f"Connected! (MTU={client.mtu_size})")
        print("Streaming heart rate — press Ctrl-C to stop.\n")
        await client.start_notify(HR_MEASUREMENT_UUID, on_hr_data)
        try:
            while True:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await client.stop_notify(HR_MEASUREMENT_UUID)

    elapsed = time.monotonic() - t0
    print(f"\nDone. {sample_count} HR samples, {rr_total} RR intervals in {elapsed:.0f}s.")


async def main():
    parser = argparse.ArgumentParser(description="Test Polar H10 BLE connection")
    parser.add_argument("--name", default=None, help="Filter by device name (e.g. 'Polar H10')")
    parser.add_argument("--address", default=None, help="Skip scan, connect directly to this MAC/UUID")
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    args = parser.parse_args()

    if args.address:
        await stream_hr(args.address)
        return

    devices = await scan_for_hr(args.name, timeout=args.scan_timeout)
    if not devices:
        print("\n❌ No Heart Rate devices found.")
        print("   • Is the strap wet and on your chest? (electrodes need moisture)")
        print("   • Is Bluetooth enabled on this Mac?")
        print("   • Check System Settings → Bluetooth")
        sys.exit(1)

    print(f"\nFound {len(devices)} device(s):\n")
    for i, d in enumerate(devices):
        print(f"  [{i}]  {d.name or '(unnamed)'}  —  {d.address}")

    if len(devices) == 1:
        target = devices[0]
    else:
        idx = int(input("\nPick a device number: "))
        target = devices[idx]

    print(f"\n→ Selected: {target.name} ({target.address})")
    await stream_hr(target.address)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped.")
