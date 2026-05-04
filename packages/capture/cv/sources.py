"""Frame sources — webcam or file. Same interface, swappable.

`cv2` is imported lazily inside the source classes so importing this module
does not require opencv to be installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    Frame = NDArray[np.uint8]
else:
    Frame = Any


@runtime_checkable
class FrameSource(Protocol):
    """Anything that yields BGR frames at a known fps."""

    fps: float

    def __iter__(self) -> Iterator[Frame]: ...


class FileSource:
    """Reads frames from an MP4 (or any cv2-supported container)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._cap: Any = None
        self.fps: float = 30.0  # populated on open()

    @contextmanager
    def open(self) -> Iterator[FileSource]:
        import cv2

        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open video: {self.path}")
        self.fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        try:
            yield self
        finally:
            self._cap.release()
            self._cap = None

    def __iter__(self) -> Iterator[Frame]:
        if self._cap is None:
            raise RuntimeError("FileSource not opened — use `with source.open():`")
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield frame


class WebcamSource:
    """Reads frames from a local webcam (cv2.VideoCapture index)."""

    def __init__(self, index: int = 0, fps: float = 30.0) -> None:
        self.index = index
        self.fps = fps
        self._cap: Any = None

    @contextmanager
    def open(self) -> Iterator[WebcamSource]:
        import cv2

        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open webcam at index {self.index}")
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        try:
            yield self
        finally:
            self._cap.release()
            self._cap = None

    def __iter__(self) -> Iterator[Frame]:
        if self._cap is None:
            raise RuntimeError("WebcamSource not opened — use `with source.open():`")
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield frame
