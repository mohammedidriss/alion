#!/usr/bin/env python3
"""imu_tool.py — set up the WitMotion WT901BLECL wrist IMUs (scan → configure → verify).

Run in YOUR terminal (Terminal / iTerm — it needs macOS Bluetooth permission;
launched from a process without it, macOS aborts with exit code 134):

  .venv/bin/python scripts/imu_tool.py scan [secs]                  find the units
  .venv/bin/python scripts/imu_tool.py info <addr>                  rate, filter, battery
  .venv/bin/python scripts/imu_tool.py configure <addr> [--rate 100] [--bandwidth 98]
  .venv/bin/python scripts/imu_tool.py calibrate <addr>             flat + still on a table
  .venv/bin/python scripts/imu_tool.py measure <addr> [secs]        real sustained rate
  .venv/bin/python scripts/imu_tool.py dual <addrA> <addrB> [secs]  both units at once
  .venv/bin/python scripts/imu_tool.py assign <addr> left|right     which wrist it lives on
  .venv/bin/python scripts/imu_tool.py factory-reset <addr> --yes   recovery

The byte-level protocol lives in `capture.imu.witmotion` (unit-tested without
hardware); this script is only the Bluetooth transport plus a guided workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from itertools import pairwise
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

REPO = Path(__file__).resolve().parents[1]
DEVICES_FILE = REPO / "data" / "imu" / "devices.json"

try:
    from capture.imu import witmotion as wm
except ModuleNotFoundError:  # interpreter without the workspace installed — use the tree
    sys.path.insert(0, str(REPO / "packages"))
    from capture.imu import witmotion as wm

WRITE_PAUSE_S = 0.15


class Link:
    """One unit's notifications: decoded samples, register replies, arrival times."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.samples: list[wm.ImuSample] = []
        self.arrivals: list[float] = []
        self.replies: list[wm.RegisterReply] = []

    def on_notify(self, _sender: object, data: bytearray) -> None:
        now = time.monotonic()
        self.buf.extend(data)
        samples, replies, rest = wm.decode(bytes(self.buf))
        self.buf[:] = rest
        self.samples.extend(samples)
        self.arrivals.extend([now] * len(samples))
        self.replies.extend(replies)

    def register(self, reg: int) -> int | None:
        for reply in reversed(self.replies):
            value = reply.get(reg)
            if value is not None:
                return value
        return None

    def rate_since(self, start: int) -> float:
        times = self.arrivals[start:]
        if len(times) < 2 or times[-1] <= times[0]:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])

    def max_gap_ms(self, start: int = 0) -> float:
        times = sorted(set(self.arrivals[start:]))
        if len(times) < 2:
            return 0.0
        return max(b - a for a, b in pairwise(times)) * 1000


def _mag(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _load_devices() -> dict[str, dict[str, str]]:
    try:
        return dict(json.loads(DEVICES_FILE.read_text()))
    except (OSError, ValueError):
        return {}


def _wrist_of(addr: str) -> str | None:
    return _load_devices().get(addr, {}).get("wrist")


def _fmt_hz(hz: float | None) -> str:
    return "unknown" if hz is None else f"{hz:g} Hz"


@asynccontextmanager
async def connected(addr: str) -> AsyncIterator[tuple[BleakClient, Link]]:
    """Connect, subscribe to the data stream, and always clean up."""
    link = Link()
    client = BleakClient(addr, timeout=20)
    try:
        await client.connect()
    except (BleakError, TimeoutError) as exc:
        raise SystemExit(
            f"\nCould not connect to {addr}: {exc}\n"
            "  • Is the unit switched on and charged?\n"
            "  • Is the WitMotion phone app connected to it? Close the app — a connected\n"
            "    unit stops advertising.\n"
            "  • Re-run `scan` to confirm the address (macOS uses per-Mac UUIDs, not MACs)."
        ) from None
    try:
        await client.start_notify(wm.NOTIFY_UUID, link.on_notify)
        yield client, link
    finally:
        try:
            await client.stop_notify(wm.NOTIFY_UUID)
        except Exception:  # unit may already be gone (e.g. after a factory reset)
            pass
        try:
            await client.disconnect()
        except Exception:
            pass


async def _write(client: BleakClient, frame: bytes, pause: float = WRITE_PAUSE_S) -> None:
    await client.write_gatt_char(wm.WRITE_UUID, frame)
    await asyncio.sleep(pause)


async def _read(
    client: BleakClient, link: Link, regs: list[int], wait: float = 1.0
) -> dict[int, int | None]:
    for reg in regs:
        await _write(client, wm.cmd_read_register(reg))
    await asyncio.sleep(wait)
    return {reg: link.register(reg) for reg in regs}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_scan(secs: int) -> None:
    print(f"Scanning {secs}s for BLE devices…")
    found = await BleakScanner.discover(timeout=secs, return_adv=True)
    units: list[tuple[int, str, str]] = []
    for dev, adv in found.values():
        name = adv.local_name or dev.name or ""
        svcs = [u.lower() for u in (adv.service_uuids or [])]
        if "WT" in name.upper() or any("ffe5" in u or "ffe4" in u for u in svcs):
            rssi = adv.rssi if adv.rssi is not None else -999
            units.append((rssi, name or "(no name)", dev.address))
    if not units:
        print("\nNo WitMotion units found.")
        print(f"({len(found)} other BLE device(s) were visible, so Bluetooth itself works.)")
        print("Checklist:")
        print("  1. Charge each unit over USB-C until the charging LED shows full.")
        print("  2. Switch it ON — the status LED should blink while it advertises.")
        print("  3. Close the WitMotion phone app (a connected unit stops advertising).")
        print("  4. Keep it within ~1 m of the Mac and scan again.")
        return
    units.sort(reverse=True)
    print(f"\nFound {len(units)} WitMotion unit(s), strongest signal first:")
    for rssi, name, addr in units:
        wrist = _wrist_of(addr)
        tag = f"   [{wrist} wrist]" if wrist else ""
        print(f"  {rssi:>4} dBm  {name:16.16}  {addr}{tag}")
    untagged = [addr for _, _, addr in units if not _wrist_of(addr)]
    if not untagged:
        print("\nEvery visible unit is assigned to a wrist. Check one with:")
        print("  .venv/bin/python scripts/imu_tool.py info <addr>")
        return
    print("\nUntagged unit(s) still need a wrist:")
    for addr in untagged:
        print(f"  .venv/bin/python scripts/imu_tool.py assign {addr} left|right")
    if len(untagged) > 1:
        print("Several are untagged — switch on one at a time to know which is which.")


async def cmd_info(addr: str) -> None:
    async with connected(addr) as (client, link):
        regs = await _read(client, link, [wm.REG_RRATE, wm.REG_BANDWIDTH, wm.REG_VOLTAGE], 0.6)
        start = len(link.samples)
        await asyncio.sleep(3.0)
        measured = link.rate_since(start)
        recent = link.samples[-50:]

    rate_code, bw_code, volt_raw = regs[wm.REG_RRATE], regs[wm.REG_BANDWIDTH], regs[wm.REG_VOLTAGE]
    configured = wm.rate_hz(rate_code) if rate_code is not None else None
    bw = wm.bandwidth_hz(bw_code) if bw_code is not None else None
    print(f"\nUnit {addr}  ({_wrist_of(addr) or 'not assigned to a wrist yet'})")
    print(f"  Output rate : {_fmt_hz(configured)} configured · {measured:.1f} Hz measured")
    print(f"  Low-pass    : {_fmt_hz(bw)}")
    if volt_raw is not None:
        volts = wm.voltage_volts(volt_raw)
        print(f"  Battery     : {volts:.2f} V (~{wm.battery_percent(volts)}%)")
    else:
        print("  Battery     : no reply")
    if recent:
        mean = sum(_mag(s.acc_g) for s in recent) / len(recent)
        print(f"  |accel|     : {mean:.2f} g  (≈1.00 g when the unit is still)")
    if not recent:
        print("  ⚠ No data frames arrived — the unit connected but isn't streaming.")
    if configured is not None and configured < 50:
        print(f"\n  ⚠ {configured:g} Hz is too slow for punches (1–2 samples per punch).")
        print(
            f"    Fix:  .venv/bin/python scripts/imu_tool.py configure {addr} --rate 100 --bandwidth 42"
        )


async def cmd_configure(addr: str, rate: float, bandwidth: int | None) -> None:
    async with connected(addr) as (client, link):
        before = await _read(client, link, [wm.REG_RRATE, wm.REG_BANDWIDTH], 0.6)
        print("Writing configuration…")
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_set_rate(rate))
        if bandwidth is not None:
            await _write(client, wm.cmd_unlock())
            await _write(client, wm.cmd_set_bandwidth(bandwidth))
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_save(), pause=0.8)

        link.replies.clear()  # only trust replies to the read-back below
        regs = [wm.REG_RRATE] + ([wm.REG_BANDWIDTH] if bandwidth is not None else [])
        after = await _read(client, link, regs, 1.0)
        start = len(link.samples)
        print("Measuring the new rate (5 s)…")
        await asyncio.sleep(5.0)
        measured = link.rate_since(start)
        gap = link.max_gap_ms(start)

    def hz_of(code: int | None) -> float | None:
        return wm.rate_hz(code) if code is not None else None

    ok_rate = after[wm.REG_RRATE] == wm.RATE_CODES[rate]
    print(
        f"\nRate     : {_fmt_hz(hz_of(before[wm.REG_RRATE]))} → {_fmt_hz(hz_of(after[wm.REG_RRATE]))}"
        f"  {'✓ saved' if ok_rate else '✗ read-back does not match'}"
    )
    if bandwidth is not None:
        bb, ba = before[wm.REG_BANDWIDTH], after.get(wm.REG_BANDWIDTH)
        ok_bw = ba == wm.BANDWIDTH_CODES[bandwidth]
        print(
            f"Low-pass : {_fmt_hz(wm.bandwidth_hz(bb) if bb is not None else None)} → "
            f"{_fmt_hz(wm.bandwidth_hz(ba) if ba is not None else None)}"
            f"  {'✓ saved' if ok_bw else '✗ read-back does not match'}"
        )
    print(f"Measured : {measured:.1f} Hz sustained over BLE · longest gap {gap:.0f} ms")
    if measured < 0.9 * rate:
        print(f"\n⚠ BLE delivered {measured:.0f} of {rate:g} Hz on this Mac. Try a lower rate:")
        print(f"   .venv/bin/python scripts/imu_tool.py configure {addr} --rate 50")
    elif ok_rate:
        unchanged = before[wm.REG_RRATE] == wm.RATE_CODES[rate] and (
            bandwidth is None or before[wm.REG_BANDWIDTH] == wm.BANDWIDTH_CODES[bandwidth]
        )
        if unchanged:
            print("\n✓ Already configured — the unit was at these settings; nothing changed.")
            _print_next_dual()
        else:
            print(f"\n✓ Configured. Next:  .venv/bin/python scripts/imu_tool.py calibrate {addr}")


def _print_next_dual() -> None:
    """Point at the both-wrists test once both units are assigned (the final setup step)."""
    by_wrist = {meta.get("wrist"): a for a, meta in _load_devices().items()}
    left, right = by_wrist.get("left"), by_wrist.get("right")
    if left and right:
        print("  Next (final setup step — wear both and shadowbox 20 s):")
        print(f"  .venv/bin/python scripts/imu_tool.py dual {left} {right}")


async def cmd_calibrate(addr: str) -> None:
    async with connected(addr) as (client, link):
        print("Lay the sensor FLAT on a table, label side up, and don't touch it.")
        for s in range(5, 0, -1):
            print(f"  starting in {s}…", end="\r", flush=True)
            await asyncio.sleep(1)
        print("Calibrating the accelerometer (6 s) — keep it still…      ")
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_calibrate_accel(True))
        await asyncio.sleep(6)
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_calibrate_accel(False))
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_save(), pause=0.8)
        start = len(link.samples)
        await asyncio.sleep(3.0)
        rest = link.samples[start:]

    if not rest:
        raise SystemExit("No data after calibration — re-run `info` to check the unit.")
    n = len(rest)
    mean = tuple(sum(s.acc_g[k] for s in rest) / n for k in range(3))
    mag = _mag((mean[0], mean[1], mean[2]))
    print(f"\nAt rest: ax={mean[0]:+.3f}  ay={mean[1]:+.3f}  az={mean[2]:+.3f} g   |a|={mag:.3f} g")
    if abs(mag - 1.0) < 0.03 and abs(mean[0]) < 0.05 and abs(mean[1]) < 0.05:
        print("✓ Calibrated — gravity reads ≈1 g straight down.")
        _print_next_dual()
    else:
        print("⚠ Not quite ≈(0, 0, ±1) g. Make sure it's flat and still, then run calibrate again.")


async def cmd_measure(addr: str, secs: int) -> None:
    async with connected(addr) as (client, link):
        regs = await _read(client, link, [wm.REG_RRATE], 0.6)
        print(f"Streaming {secs}s — shake the unit to watch it respond…")
        start = len(link.samples)
        await asyncio.sleep(secs)
        measured = link.rate_since(start)
        gap = link.max_gap_ms(start)
        data = link.samples[start:]

    code = regs[wm.REG_RRATE]
    configured = wm.rate_hz(code) if code is not None else None
    print(
        f"\nConfigured {_fmt_hz(configured)} · measured {measured:.1f} Hz · "
        f"{len(data)} samples · longest gap {gap:.0f} ms"
    )
    if data:
        peak = max(_mag(s.acc_g) for s in data)
        print(f"Peak |accel| {peak:.2f} g  (shaking should push this well above 1 g)")
        for s in data[:3]:
            print(
                "  acc",
                tuple(round(x, 2) for x in s.acc_g),
                " gyro",
                tuple(round(x, 1) for x in s.gyro_dps),
            )
    if configured and measured < 0.9 * configured:
        print(f"⚠ Below {configured:g} Hz — BLE can't keep up; consider --rate 50.")


# An axis at ≥ this many g is pinned against the ±16 g range: the true value was higher.
CLIP_G = 15.5


async def _stream(addr: str, secs: int) -> tuple[str, float | None, float, float, int, float, int]:
    async with connected(addr) as (client, link):
        regs = await _read(client, link, [wm.REG_RRATE], 0.6)
        start = len(link.samples)
        await asyncio.sleep(secs)
        code = regs[wm.REG_RRATE]
        configured = wm.rate_hz(code) if code is not None else None
        data = link.samples[start:]
        peak = max((_mag(s.acc_g) for s in data), default=0.0)
        clipped = sum(1 for s in data if max(abs(a) for a in s.acc_g) >= CLIP_G)
        return (
            addr,
            configured,
            link.rate_since(start),
            link.max_gap_ms(start),
            len(data),
            peak,
            clipped,
        )


async def cmd_dual(addr_a: str, addr_b: str, secs: int) -> None:
    print(f"Streaming BOTH units for {secs}s at once (this is the real session load)…")
    print(
        "Tip: wear them and shadowbox — that's the realistic test (motion + your body in the way)."
    )
    results = await asyncio.gather(_stream(addr_a, secs), _stream(addr_b, secs))
    ok = True
    any_clipped = False
    print()
    for addr, configured, measured, gap, n, peak, clipped in results:
        wrist = _wrist_of(addr) or "?"
        good = configured is not None and measured >= 0.9 * configured
        ok = ok and good
        any_clipped = any_clipped or clipped > 0
        clip_note = f" · ⚠ {clipped} clipped" if clipped else ""
        print(
            f"  {wrist:>5} wrist  {_fmt_hz(configured)} → {measured:.1f} Hz · gap {gap:.0f} ms · "
            f"{n} samples · peak {peak:.1f} g{clip_note}  {'✓' if good else '⚠'}"
        )
    if ok:
        print("\n✓ Both units sustain their rate together — ready for recording.")
    else:
        print("\n⚠ At least one unit fell below 90% of its rate with both streaming.")
        print("  Lower both to 50 Hz with `configure <addr> --rate 50`, then re-run dual.")
    if any_clipped:
        print("⚠ Some samples hit the ±16 g limit: hard punches saturate the accelerometer.")
        print(
            "  Counting and typing still work; peak-g on those punches is a floor, not the true value."
        )


def cmd_assign(addr: str, wrist: str) -> None:
    devices = _load_devices()
    for other, meta in list(devices.items()):  # one unit per wrist
        if other != addr and meta.get("wrist") == wrist:
            del devices[other]
    devices[addr] = {"wrist": wrist}
    DEVICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICES_FILE.write_text(json.dumps(devices, indent=2) + "\n")
    print(f"✓ {addr} → {wrist} wrist   (saved to {DEVICES_FILE.relative_to(REPO)})")
    for a, meta in devices.items():
        print(f"    {meta.get('wrist', '?'):>5}: {a}")


async def cmd_factory_reset(addr: str, yes: bool) -> None:
    if not yes:
        raise SystemExit(
            "This restores factory defaults (output rate back to 10 Hz). "
            "Re-run with --yes to confirm."
        )
    async with connected(addr) as (client, _link):
        await _write(client, wm.cmd_unlock())
        await _write(client, wm.cmd_factory_reset(), pause=1.0)
    print("Factory defaults restored. Power-cycle the unit, then run configure + calibrate again.")


def main() -> None:
    p = argparse.ArgumentParser(description="Set up the WT901BLECL wrist IMUs.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("secs", nargs="?", type=int, default=8)
    s = sub.add_parser("info")
    s.add_argument("addr")
    s = sub.add_parser("configure")
    s.add_argument("addr")
    s.add_argument("--rate", type=float, default=100)
    s.add_argument("--bandwidth", type=int, default=None)
    s = sub.add_parser("calibrate")
    s.add_argument("addr")
    s = sub.add_parser("measure")
    s.add_argument("addr")
    s.add_argument("secs", nargs="?", type=int, default=15)
    s = sub.add_parser("dual")
    s.add_argument("addr_a")
    s.add_argument("addr_b")
    s.add_argument("secs", nargs="?", type=int, default=20)
    s = sub.add_parser("assign")
    s.add_argument("addr")
    s.add_argument("wrist", choices=["left", "right"])
    s = sub.add_parser("factory-reset")
    s.add_argument("addr")
    s.add_argument("--yes", action="store_true")
    a = p.parse_args()

    if a.cmd == "scan":
        asyncio.run(cmd_scan(a.secs))
    elif a.cmd == "info":
        asyncio.run(cmd_info(a.addr))
    elif a.cmd == "configure":
        rate = int(a.rate) if float(a.rate).is_integer() else a.rate
        asyncio.run(cmd_configure(a.addr, rate, a.bandwidth))
    elif a.cmd == "calibrate":
        asyncio.run(cmd_calibrate(a.addr))
    elif a.cmd == "measure":
        asyncio.run(cmd_measure(a.addr, a.secs))
    elif a.cmd == "dual":
        asyncio.run(cmd_dual(a.addr_a, a.addr_b, a.secs))
    elif a.cmd == "assign":
        cmd_assign(a.addr, a.wrist)
    elif a.cmd == "factory-reset":
        asyncio.run(cmd_factory_reset(a.addr, a.yes))


if __name__ == "__main__":
    main()
