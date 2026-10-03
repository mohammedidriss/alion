"""The wrist-IMU pair this Mac knows about — written by `scripts/imu_tool.py assign`.

`data/imu/devices.json` maps each unit's Bluetooth address to its wrist, plus the
fighter who wears the pair:

    {"<address>": {"wrist": "left", "fighter_id": "<uuid>"}, ...}

It's local config, not database data: macOS Bluetooth addresses are per-Mac
UUIDs, so the file is gitignored and the API reads it from disk.
"""

from __future__ import annotations

import json
from pathlib import Path

DEVICES_FILE = Path("data/imu/devices.json")


def load() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(DEVICES_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def units() -> list[dict[str, str | None]]:
    """[{hand, address, name}] for assigned units, left first. `name` is the BLE name
    `imu_tool.py scan` last saw (both WT901s advertise "WT901BLE68")."""
    out: list[dict[str, str | None]] = [
        {"hand": meta["wrist"], "address": addr, "name": meta.get("name")}
        for addr, meta in load().items()
        if meta.get("wrist")
    ]
    return sorted(out, key=lambda u: str(u["hand"]))


def units_by_hand() -> dict[str, str]:
    """{"left": address, "right": address} for the units that have a wrist."""
    return {meta["wrist"]: addr for addr, meta in load().items() if meta.get("wrist")}


def owner_id() -> str | None:
    """The fighter wearing the pair (None if unassigned or the units disagree)."""
    owners = {meta.get("fighter_id") for meta in load().values()}
    return owners.pop() if len(owners) == 1 and None not in owners else None


def set_owner(fighter_id: str) -> None:
    devices = load()
    for meta in devices.values():
        meta["fighter_id"] = fighter_id
    DEVICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICES_FILE.write_text(json.dumps(devices, indent=2) + "\n")
