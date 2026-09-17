"""Renderer protocol: something that yields full 320x480 RGB frames when the
picture changed. The device loop diffs them and pushes only what moved."""
from __future__ import annotations

from typing import Protocol

from PIL import Image

W, H = 320, 480


class Renderer(Protocol):
    name: str

    def start(self) -> None: ...

    def poll(self, timeout: float) -> Image.Image | None:
        """Return a new full frame if anything changed within `timeout`
        seconds, else None. May block up to `timeout`."""
        ...

    def stop(self) -> None: ...
