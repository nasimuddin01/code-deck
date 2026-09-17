"""Driver for TURZX 3.5" USB smart screen (Turing Smart Screen rev A protocol).

Device: /dev/cu.usbmodemUSB35INCHIPSV21 (serial number USB35INCHIPSV2)
Native panel: 320x480 portrait. Pixels: RGB565 little-endian.
Protocol: 6-byte command frames with 10-bit packed coordinates.
"""
from __future__ import annotations

import glob
import time

import numpy as np
import serial
from PIL import Image

# Commands (rev A)
RESET = 101
CLEAR = 102
SCREEN_OFF = 108
SCREEN_ON = 109
SET_BRIGHTNESS = 110
SET_ORIENTATION = 121
DISPLAY_BITMAP = 197

PORTRAIT = 0
REVERSE_PORTRAIT = 1
LANDSCAPE = 2
REVERSE_LANDSCAPE = 3

NATIVE_W, NATIVE_H = 320, 480


def find_port() -> str:
    matches = glob.glob("/dev/cu.usbmodemUSB35INCH*")
    if not matches:
        raise RuntimeError("TURZX screen not found (no /dev/cu.usbmodemUSB35INCH*)")
    return matches[0]


class TurzxScreen:
    def __init__(self, port: str | None = None, orientation: int = PORTRAIT):
        self.ser = serial.Serial(port or find_port(), 115200, timeout=1, rtscts=True)
        # settle: port-open toggles DTR; commands sent too early desync the MCU
        time.sleep(1.5)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.orientation = orientation
        self.pace = 0.002  # seconds between chunks; guards against CDC buffer overrun
        if orientation != PORTRAIT:
            self.set_orientation(orientation)

    @property
    def width(self) -> int:
        return NATIVE_H if self.orientation in (LANDSCAPE, REVERSE_LANDSCAPE) else NATIVE_W

    @property
    def height(self) -> int:
        return NATIVE_W if self.orientation in (LANDSCAPE, REVERSE_LANDSCAPE) else NATIVE_H

    def _cmd(self, cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> None:
        buf = bytearray(6)
        buf[0] = x >> 2
        buf[1] = ((x & 3) << 6) + (y >> 4)
        buf[2] = ((y & 15) << 4) + (ex >> 6)
        buf[3] = ((ex & 63) << 2) + (ey >> 8)
        buf[4] = ey & 255
        buf[5] = cmd
        self.ser.write(bytes(buf))

    def set_orientation(self, orientation: int) -> None:
        self.orientation = orientation
        buf = bytearray(16)
        buf[5] = SET_ORIENTATION
        buf[6] = orientation + 100
        buf[7] = self.width >> 8
        buf[8] = self.width & 255
        buf[9] = self.height >> 8
        buf[10] = self.height & 255
        self.ser.write(bytes(buf))

    def set_brightness(self, percent: int) -> None:
        # Panel scale is inverted: 0 = brightest, 255 = darkest.
        self._cmd(SET_BRIGHTNESS, int(255 - (max(0, min(100, percent)) / 100) * 255))

    def clear(self) -> None:
        saved = self.orientation
        self.set_orientation(PORTRAIT)  # panel quirk: CLEAR needs portrait
        self._cmd(CLEAR)
        self.set_orientation(saved)

    def screen_on(self) -> None:
        self._cmd(SCREEN_ON)

    def screen_off(self) -> None:
        self._cmd(SCREEN_OFF)

    # Clone firmware appears to react to protocol command byte values even
    # inside bitmap payload. Remap any pixel whose RGB565-LE bytes contain one
    # to the nearest visually-identical clean color.
    FORBIDDEN = frozenset([40, 41, 69, 255] + list(range(101, 111)) + [121, 122, 130, 131]
                          + list(range(160, 181)) + list(range(194, 213)))
    _LUT: np.ndarray | None = None

    @classmethod
    def _lut(cls) -> np.ndarray:
        if cls._LUT is None:
            lut = np.arange(65536, dtype=np.uint16)
            forbidden = cls.FORBIDDEN
            for v in range(65536):
                if (v & 0xFF) not in forbidden and (v >> 8) not in forbidden:
                    continue
                r, g, b = v >> 11, (v >> 5) & 0x3F, v & 0x1F
                best, best_cost = v, 1 << 30
                for dr in (0, -1, 1, -2, 2):
                    nr = r + dr
                    if not 0 <= nr <= 31:
                        continue
                    for dg in (0, -1, 1, -2, 2):
                        ng = g + dg
                        if not 0 <= ng <= 63:
                            continue
                        for db in (0, -1, 1, -2, 2):
                            nb = b + db
                            if not 0 <= nb <= 31:
                                continue
                            nv = (nr << 11) | (ng << 5) | nb
                            if (nv & 0xFF) in forbidden or (nv >> 8) in forbidden:
                                continue
                            cost = (dr * 2) ** 2 + dg ** 2 + (db * 2) ** 2
                            if cost < best_cost:
                                best, best_cost = nv, cost
                lut[v] = best
            cls._LUT = lut
        return cls._LUT

    @classmethod
    def _to_rgb565le(cls, image: Image.Image) -> bytes:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
        r, g, b = rgb[..., 0] >> 3, rgb[..., 1] >> 2, rgb[..., 2] >> 3
        px = ((r << 11) | (g << 5) | b).astype(np.uint16)
        lut = cls._lut()
        px = lut[px]
        # kill identical-pixel runs: checkerboard-toggle one LSB, falling back
        # through green -> blue -> red until the variant survives the byte filter
        c1 = lut[px ^ 32]     # green LSB
        c2 = lut[px ^ 1]      # blue LSB
        c3 = lut[px ^ 2048]   # red LSB
        alt = np.where(c1 != px, c1, np.where(c2 != px, c2, c3))
        h, w = px.shape
        yy, xx = np.mgrid[0:h, 0:w]
        px = np.where(((yy + xx) & 1).astype(bool), alt, px).astype(np.uint16)
        return px.astype("<u2").tobytes()

    def draw(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        w = min(image.width, self.width - x)
        h = min(image.height, self.height - y)
        if (w, h) != image.size:
            image = image.crop((0, 0, w, h))
        self._cmd(DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1)
        data = self._to_rgb565le(image)
        chunk = self.width * 8
        for i in range(0, len(data), chunk):
            self.ser.write(data[i:i + chunk])
            self.ser.flush()
            if self.pace:
                time.sleep(self.pace)
        time.sleep(0.02)

    @classmethod
    def open_with_reset(cls, orientation: int = PORTRAIT) -> "TurzxScreen":
        """Open, hardware-reset the panel, and reopen once it re-enumerates."""
        scr = cls(orientation=orientation)
        scr.reset()
        deadline = time.time() + 25
        time.sleep(3)
        while time.time() < deadline:
            try:
                return cls(port=find_port(), orientation=orientation)
            except (RuntimeError, serial.SerialException):
                time.sleep(1)
        raise RuntimeError("screen did not re-enumerate after reset")

    def hello(self) -> bytes:
        """Ask the panel for its sub-revision (next-gen clones answer, Turing stays silent)."""
        self.ser.write(bytes([69] * 6))
        resp = self.ser.read(6)
        self.ser.reset_input_buffer()
        return resp

    def reset(self) -> None:
        """Hardware reset; the device re-enumerates, so the port must be reopened."""
        self._cmd(RESET)
        self.ser.close()

    def close(self) -> None:
        self.ser.close()
