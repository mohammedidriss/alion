"""Is this computer's disk encrypted? (ADR-044)

Alion keeps its data on this computer and doesn't encrypt the database itself yet
(ADR-002); full-disk encryption is what protects it at rest meanwhile. This only
reads the status — turning encryption on is the owner's job, in the system's own
settings. macOS: `fdesetup status` (no admin rights needed). Elsewhere: unknown.
"""

from __future__ import annotations

import platform
import subprocess
import threading
import time
from typing import Literal

Status = Literal["on", "off", "unknown"]
_CACHE_S = 600.0
_lock = threading.Lock()
_cached: tuple[float, Status] | None = None


def _check() -> Status:
    if platform.system() != "Darwin":
        return "unknown"
    try:
        out = subprocess.run(
            ["/usr/bin/fdesetup", "status"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if "FileVault is On" in out:
        return "on"
    if "FileVault is Off" in out:
        return "off"
    return "unknown"


def status() -> Status:
    global _cached
    with _lock:
        if _cached is not None and time.monotonic() - _cached[0] < _CACHE_S:
            return _cached[1]
    s = _check()
    with _lock:
        _cached = (time.monotonic(), s)
    return s
