"""Live BLE source for an instrumented mouthguard (ADR 007).

Mirrors the threading/queue lifecycle of `capture/hrv/polar.py`: a bleak async
loop runs on a private daemon thread, the consuming thread iterates
`HeadImpactEvent`s synchronously through a thread-safe queue.

Unlike the BLE Heart Rate service, instrumented-mouthguard impact reporting is
**not** a standardised GATT profile — every vendor (Prevent Biometrics, Stanford
MiG-class, etc.) frames its impact packets differently. So the raw-packet →
`ImpactReading` decode is an injected seam (`decode`), not hard-coded here. The
reusable part — connect, notify, T_0 tagging, queue plumbing — lives in this
class; the vendor-specific byte layout is supplied by the caller.

Each impact is tagged against the session `SessionClock` T_0 (ADR 006) using the
OS arrival time: `t_ms = clock.offset_from_wall(now_utc())`.

Requires `bleak` (lazy-imported).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

from capture.mouthguard.replay import ImpactReading
from common import SessionClock, get_logger, now_utc
from contracts import HeadImpactEvent

log = get_logger(__name__)

# Type of the vendor-specific decoder: raw BLE payload → one reading, or None
# for a packet that is not an impact (status/heartbeat frames).
ImpactDecoder = Callable[[bytearray], ImpactReading | None]


def impact_event_from_reading(
    session_id: UUID,
    reading: ImpactReading,
    t_ms: float,
) -> HeadImpactEvent:
    """Assemble a `HeadImpactEvent` from a decoded reading + a T_0 offset.

    Pure and side-effect free — the single place stream sources turn an
    `ImpactReading` into a stored event, so the mapping is tested in one spot.
    """
    return HeadImpactEvent(
        session_id=session_id,
        t_ms=t_ms,
        peak_linear_accel_g=reading.peak_linear_accel_g,
        peak_rotational_vel_rad_s=reading.peak_rotational_vel_rad_s,
        peak_rotational_accel_rad_s2=reading.peak_rotational_accel_rad_s2,
        location=reading.location,
        device_id=reading.device_id,
        confidence=reading.confidence,
    )


def _decode_not_implemented(_data: bytearray) -> ImpactReading | None:
    raise NotImplementedError(
        "No impact decoder supplied. Instrumented-mouthguard impact framing is "
        "vendor-specific; pass a `decode` callable that maps this device's BLE "
        "payload to an ImpactReading."
    )


async def scan_for_impact_devices(timeout: float = 8.0) -> list[dict[str, Any]]:
    """Scan for nearby BLE devices (returns name + address).

    No service-UUID filter — impact reporting has no standard service, so the
    caller matches the device by name/address. Returns dicts: name, address.
    """
    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=timeout)
    return [{"name": d.name or "(unnamed)", "address": d.address} for d in devices]


class MouthguardBleSource:
    """Iterable BLE source yielding `HeadImpactEvent`s from a mouthguard.

    Runs a bleak async loop on a private thread; the consuming thread iterates
    synchronously via a thread-safe queue (same shape as `PolarH10Source`).
    """

    def __init__(
        self,
        session_id: UUID,
        address: str,
        clock: SessionClock,
        *,
        characteristic_uuid: str,
        decode: ImpactDecoder = _decode_not_implemented,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.session_id = session_id
        self.address = address
        self.clock = clock
        self.characteristic_uuid = characteristic_uuid
        self.decode = decode
        self._stop_event = stop_event or threading.Event()
        self._connected = threading.Event()
        self._error: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def stop(self) -> None:
        self._stop_event.set()

    def __iter__(self) -> Iterator[HeadImpactEvent]:
        q: queue.Queue[HeadImpactEvent | None] = queue.Queue(maxsize=500)

        ble_thread = threading.Thread(
            target=self._run_async_loop,
            args=(q,),
            daemon=True,
            name=f"mouthguard-ble-{self.session_id}",
        )
        ble_thread.start()

        if not self._connected.wait(timeout=15.0):
            raise RuntimeError(
                f"Failed to connect to mouthguard at {self.address} within 15s. "
                f"Error: {self._error or 'timeout'}"
            )

        log.info(
            "mouthguard.connected",
            extra={"_ctx_session_id": str(self.session_id), "_ctx_device": self.address},
        )

        while not self._stop_event.is_set():
            try:
                event = q.get(timeout=2.0)
            except queue.Empty:
                if not ble_thread.is_alive():
                    log.warning(
                        "mouthguard.ble_thread_died",
                        extra={"_ctx_session_id": str(self.session_id)},
                    )
                    break
                continue
            if event is None:
                break  # sentinel — BLE disconnected
            yield event

    def _run_async_loop(self, q: queue.Queue[HeadImpactEvent | None]) -> None:
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._stream_ble(q))
        except Exception as exc:
            log.exception(
                "mouthguard.ble_error: %s",
                exc,
                extra={"_ctx_session_id": str(self.session_id)},
            )
            self._error = str(exc)
        finally:
            q.put(None)  # sentinel
            loop.close()

    async def _stream_ble(self, q: queue.Queue[HeadImpactEvent | None]) -> None:
        import asyncio

        from bleak import BleakClient

        def on_impact(_sender: object, data: bytearray) -> None:
            reading = self.decode(data)
            if reading is None:
                return  # not an impact frame
            t_ms = self.clock.offset_from_wall(now_utc())
            event = impact_event_from_reading(self.session_id, reading, t_ms)
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # drop if consumer is slow

        async with BleakClient(self.address) as client:
            self._connected.set()
            await client.start_notify(self.characteristic_uuid, on_impact)
            try:
                while not self._stop_event.is_set():
                    if not client.is_connected:
                        log.warning(
                            "mouthguard.disconnected",
                            extra={"_ctx_session_id": str(self.session_id)},
                        )
                        break
                    await asyncio.sleep(0.5)
            finally:
                if client.is_connected:
                    await client.stop_notify(self.characteristic_uuid)
