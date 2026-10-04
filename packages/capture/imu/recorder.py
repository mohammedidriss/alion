"""Live recorder for the WT901 wrist IMUs — runs as its own process.

    python -m capture.imu.recorder --rate 100 --unit left=<addr> --unit right=<addr>

Writes one JSON object per line to stdout:

    {"k":"s","h":"left","t":<epoch ms>,"a":[ax,ay,az],"g":[gx,gy,gz]}   a sample (g, °/s)
    {"k":"st","h":"left","connected":true,"battery_v":4.21}              unit status
    {"k":"err","h":"left","msg":"…"}                                     error (it retries)

Sample times come from `SampleClock` (the sensor's own 100 Hz grid), not BLE
arrival, so they line up with the video to a few milliseconds.

Why a separate process: on macOS, CoreBluetooth aborts any process that lacks
Bluetooth permission (SIGABRT, exit 134). Isolated here, that costs the session
its IMU stream — never the API server that launched it. It also exits if that
parent dies, so a sensor is never left stuck connected (a connected unit stops
advertising and can't be found again until power-cycled).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from typing import Any

from bleak import BleakClient

from capture.imu import witmotion as wm
from capture.imu.clock import SampleClock


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


async def _run_unit(hand: str, address: str, rate: float, stop: asyncio.Event) -> None:
    backoff = 1.0
    while not stop.is_set():
        clock = SampleClock(rate)  # a new connection restarts the sample index
        buf = bytearray()

        def on_notify(
            _sender: object,
            data: bytearray,
            clock: SampleClock = clock,
            buf: bytearray = buf,
        ) -> None:
            arrival = time.time()
            buf.extend(data)
            samples, replies, rest = wm.decode(bytes(buf))
            buf[:] = rest
            for reply in replies:
                raw = reply.get(wm.REG_VOLTAGE)
                if raw is not None:
                    volts = round(wm.voltage_volts(raw), 2)
                    _emit({"k": "st", "h": hand, "connected": True, "battery_v": volts})
            if not samples:
                return
            times = clock.feed(arrival, len(samples))
            lines = [
                json.dumps(
                    {
                        "k": "s",
                        "h": hand,
                        "t": round(t * 1000.0, 2),
                        "a": [round(x, 4) for x in s.acc_g],
                        "g": [round(x, 2) for x in s.gyro_dps],
                    },
                    separators=(",", ":"),
                )
                for t, s in zip(times, samples, strict=True)
            ]
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

        try:
            async with BleakClient(address, timeout=20) as client:
                await client.start_notify(wm.NOTIFY_UUID, on_notify)
                _emit({"k": "st", "h": hand, "connected": True})
                await client.write_gatt_char(wm.WRITE_UUID, wm.cmd_read_register(wm.REG_VOLTAGE))
                backoff = 1.0
                while not stop.is_set() and client.is_connected:
                    await asyncio.sleep(0.5)
        except Exception as exc:  # out of range, switched off, busy — report and retry
            _emit({"k": "err", "h": hand, "msg": str(exc)[:200] or type(exc).__name__})
        _emit({"k": "st", "h": hand, "connected": False})
        if stop.is_set():
            break
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 10.0)


async def _watch_parent(stop: asyncio.Event) -> None:
    parent = os.getppid()
    while not stop.is_set():
        if os.getppid() != parent:  # re-parented: the API is gone
            stop.set()
        await asyncio.sleep(1.0)


async def _main(units: dict[str, str], rate: float) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    tasks = [
        asyncio.create_task(_watch_parent(stop)),
        *(asyncio.create_task(_run_unit(hand, addr, rate, stop)) for hand, addr in units.items()),
    ]
    await stop.wait()
    # Cancel rather than wait: a unit that's off leaves its task inside a 20 s
    # BleakClient connect (or a backoff sleep), and the API kills us after 5 s.
    # Cancelling a connected unit still disconnects it (BleakClient.__aexit__).
    for t in tasks:
        t.cancel()
    await asyncio.wait(tasks, timeout=3.0)


def main() -> None:
    p = argparse.ArgumentParser(description="Stream the WT901 wrist IMUs as JSON lines.")
    p.add_argument("--rate", type=float, default=100.0)
    p.add_argument("--unit", action="append", default=[], help="hand=address (repeatable)")
    a = p.parse_args()
    units = dict(u.split("=", 1) for u in a.unit)
    if not units:
        p.error("at least one --unit hand=address is required")
    asyncio.run(_main(units, a.rate))


if __name__ == "__main__":
    main()
