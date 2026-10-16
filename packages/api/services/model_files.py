"""Saving a trained model so a reader never sees half a file (ADR-064): written
beside its final name, then moved into place in one step."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def dump(obj: Any, path: Path) -> None:
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]

    tmp = path.with_name(f".{path.name}.tmp")
    joblib.dump(obj, tmp)
    os.replace(tmp, path)


def write_json(data: Any, path: Path) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)
