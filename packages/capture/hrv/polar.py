"""Polar H10 BLE driver — live RR interval streaming via bleak.

Yields `HRSample` events as they arrive over Bluetooth LE, matching the
same interface as `CsvReplaySource`. The HRV runner consumes either
source interchangeably.

Requires `bleak` (installed via `uv pip install bleak`).
"""

from __future__ import annotations

import asyncio
import struct
import threading
import time
from collections.abc import Iterator
from uuid import UUID

from common import get_logger
from contracts import HRSample

log = get_logger(__name__)

# Bluetooth SIG Heart Rate Service / Measurement UUIDs
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_hr_measurement(data: bytearray) -> dict:
    """Parse a BLE Heart Rate Measurement characteristic (BLE spec §3.105).

    Returns:
        hr_bpm:  instantaneous heart rate
        rr_ms:   list of RR intervals in milliseconds (may be empty)
        contact: True/False/None
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

    if energy_present:
        offset += 2  # skip energy expenditure

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
    }


async def scan_for_hr_devices(timeout: float = 8.0) -> list[dict]:
    """Scan for BLE devices advertising the Heart Rate service.

    Returns a list of dicts with keys: name, address.
    """
    from bleak import BleakScanner

    devices = await BleakScanner.discover(
        timeout=timeout,
        service_uuids=[HR_SERVICE_UUID],
    )
    return [
        {"name": d.name or "(unnamed)", "address": d.address}
        for d in devices
    ]


class PolarH10Source:
    """Iterable BLE source that yields HRSample events from a Polar H10.

    Runs a bleak async loop on a private thread. The consuming thread
    (hrv_runner) iterates synchronously via a thread-safe queue.
    """

    def __init__(
        self,
        session_id: UUID,
        address: str,
        *,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.session_id = session_id
        self.address = address
        self._stop_event = stop_event or threading.Event()
        self._queue: asyncio.Queue[HRSample | None] = asyncio.Queue()
        self._thread_queue: "ThreadQueue[HRSample | None] | None" = None
        self._device_name: str | None = None
        self._connected = threading.Event()
        self._error: str | None = None

    @property
    def device_name(self) -> str | None:
        return self._device_name

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def __iter__(self) -> Iterator[HRSample]:
        import queue

        q: queue.Queue[HRSample | None] = queue.Queue(maxsize=500)
        self._thread_queue = q  # type: ignore[assignment]

        # Launch the async BLE loop on a background thread.
        ble_thread = threading.Thread(
            target=self._run_async_loop,
            args=(q,),
            daemon=True,
            name=f"polar-ble-{self.session_id}",
        )
        ble_thread.start()

        # Wait for connection (up to 15 seconds).
        if not self._connected.wait(timeout=15.0):
            raise RuntimeError(
                f"Failed to connect to Polar H10 at {self.address} within 15s. "
                f"Error: {self._error or 'timeout'}"
            )

        log.info(
            "polar.connected",
            extra={
                "_ctx_session_id": str(self.session_id),
                "_ctx_device": self._device_name or self.address,
            },
        )

        # Yield samples from the thread-safe queue.
        while not self._stop_event.is_set():
            try:
                sample = q.get(timeout=2.0)
            except queue.Empty:
                # Check if the BLE thread died.
                if not ble_thread.is_alive():
                    log.warning("polar.ble_thread_died", extra={
                        "_ctx_session_id": str(self.session_id),
                    })
                    break
                continue
            if sample is None:
                break  # sentinel — BLE disconnected
            yield sample

    def _run_async_loop(self, q: "queue.Queue[HRSample | None]") -> None:
        """Runs in a daemon thread — owns its own asyncio event loop."""
        import queue

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._stream_ble(q))
        except Exception as exc:
            log.exception("polar.ble_error: %s", exc, extra={
                "_ctx_session_id": str(self.session_id),
            })
            self._error = str(exc)
        finally:
            q.put(None)  # sentinel
            loop.close()

    async def _stream_ble(self, q: "queue.Queue[HRSample | None]") -> None:
        import queue

        from bleak import BleakClient

        t0 = time.monotonic()
        running_t_ms = 0.0  # cumulative time from RR intervals

        def on_hr_data(_sender: int, data: bytearray) -> None:
            nonlocal running_t_ms
            parsed = parse_hr_measurement(data)
            rr_list = parsed["rr_ms"]
            hr_bpm = parsed["hr_bpm"]

            if not rr_list:
                # HR-only notification (no RR) — emit a single sample
                # using wall-clock elapsed and HR-derived pseudo-RR.
                wall_ms = (time.monotonic() - t0) * 1000.0
                pseudo_rr = 60_000.0 / max(hr_bpm, 30)
                sample = HRSample(
                    session_id=self.session_id,
                    t_ms=wall_ms,
                    rr_ms=pseudo_rr,
                    hr_bpm=float(hr_bpm),
                )
                try:
                    q.put_nowait(sample)
                except queue.Full:
                    pass
                return

            for rr_ms in rr_list:
                running_t_ms += rr_ms
                sample = HRSample(
                    session_id=self.session_id,
                    t_ms=running_t_ms,
                    rr_ms=rr_ms,
                    hr_bpm=60_000.0 / max(rr_ms, 1.0),
                )
                try:
                    q.put_nowait(sample)
                except queue.Full:
                    pass  # drop oldest if consumer is slow

        async with BleakClient(self.address) as client:
            self._device_name = self.address
            # Try to read the device name characteristic
            try:
                name_bytes = await client.read_gatt_char(
                    "00002a00-0000-1000-8000-00805f9b34fb"
                )
                self._device_name = name_bytes.decode("utf-8").strip()
            except Exception:
                pass

            self._connected.set()

            await client.start_notify(HR_MEASUREMENT_UUID, on_hr_data)
            try:
                # Block until stop is requested or disconnect.
                while not self._stop_event.is_set():
                    if not client.is_connected:
                        log.warning("polar.disconnected", extra={
                            "_ctx_session_id": str(self.session_id),
                        })
                        break
                    await asyncio.sleep(0.5)
            finally:
                if client.is_connected:
                    await client.stop_notify(HR_MEASUREMENT_UUID)
