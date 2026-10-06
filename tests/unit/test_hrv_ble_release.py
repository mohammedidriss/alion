"""A Polar stream that fails must let go of the strap.

The H10 takes two connections. A connect attempt that timed out kept its BLE
thread running; if it connected late it held the strap with nobody reading, and
every retry after that failed while the strap looked connected.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from uuid import uuid4

import pytest

from contracts import HRSample


def test_a_failed_ble_stream_tells_its_connection_to_let_go(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import capture.hrv.polar as polar
    from api.services import hrv_runner

    seen: list[threading.Event] = []

    class NeverConnects:
        def __init__(self, *, session_id: object, address: str, stop_event: threading.Event):
            seen.append(stop_event)

        def __iter__(self) -> Iterator[HRSample]:
            raise RuntimeError("Failed to connect to Polar H10 at X within 15s. Error: timeout")

    monkeypatch.setattr(polar, "PolarH10Source", NeverConnects)
    sid = uuid4()
    assert hrv_runner.start_ble(sid, "X", None, write_rows=lambda rows: None)
    deadline = time.time() + 5
    while hrv_runner.is_running(sid) and time.time() < deadline:
        time.sleep(0.01)
    assert not hrv_runner.is_running(sid)
    assert seen and seen[0].is_set()  # the background BLE thread is told to disconnect
    assert "Failed to connect" in (hrv_runner.last_error(sid) or "")
