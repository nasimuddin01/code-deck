"""Locate libusb-1.0 and build the pyusb backend lazily.

The backend is created on first use, not at import, so `code-deck doctor` and
device-less runs work on machines without libusb and can report the problem.
"""
from __future__ import annotations

import ctypes.util
import os
import sys
from functools import lru_cache

ENV_VAR = "CODE_DECK_LIBUSB"
CANDIDATES = (
    "/opt/homebrew/lib/libusb-1.0.dylib",             # macOS arm64 Homebrew
    "/usr/local/lib/libusb-1.0.dylib",                # macOS x86_64 Homebrew
    "/usr/lib/x86_64-linux-gnu/libusb-1.0.so.0",
    "/usr/lib/aarch64-linux-gnu/libusb-1.0.so.0",     # Raspberry Pi OS 64-bit
    "/usr/lib/arm-linux-gnueabihf/libusb-1.0.so.0",   # Raspberry Pi OS 32-bit
)
INSTALL_HINT = "brew install libusb" if sys.platform == "darwin" else "sudo apt install libusb-1.0-0"


class LibusbNotFound(RuntimeError):
    pass


def find_libusb(env: os._Environ | dict = os.environ,
                candidates: tuple[str, ...] = CANDIDATES) -> str | None:
    """Path (or loader name) of libusb-1.0, or None. Env override wins."""
    override = env.get(ENV_VAR)
    if override:
        return override if os.path.exists(override) else None
    found = ctypes.util.find_library("usb-1.0")
    if found:
        return found
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


@lru_cache(maxsize=1)
def backend():
    path = find_libusb()
    if path is None:
        raise LibusbNotFound(
            f"libusb-1.0 not found. Install it ({INSTALL_HINT}) "
            f"or point {ENV_VAR} at the library file.")
    import usb.backend.libusb1
    be = usb.backend.libusb1.get_backend(find_library=lambda _: path)
    if be is None:
        raise LibusbNotFound(f"libusb found at {path} but could not be loaded")
    return be
