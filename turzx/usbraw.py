"""Raw USB bulk driver for the TURZX 3.5" smart screen.

Bypasses the macOS CDC serial driver (which drops bytes on sustained complex
writes and shears the image) by writing protocol bytes straight to bulk OUT
endpoint 0x03 via libusb -- one bulk transfer per bitmap, throttled by the
device's own USB NAKs, exactly like the Windows usbser path. libusb seizes the
interface on macOS without sudo once the /dev/cu.* serial port is closed.

Pixels are filtered through pixels.to_rgb565le so a residual desync cannot fire
a screen-off/brightness/reset command hidden inside pixel data.
"""
from __future__ import annotations
import time
import usb.core
import usb.util
import usb.backend.libusb1
from PIL import Image

from turzx import pixels

VID, PID = 0x1A86, 0x5722
BULK_OUT = 0x03
DATA_IFACE = 1
DISPLAY_BITMAP = 197
NATIVE_W, NATIVE_H = 320, 480

_BACKEND = usb.backend.libusb1.get_backend(
    find_library=lambda x: "/opt/homebrew/lib/libusb-1.0.dylib")


class UsbRaw:
    def __init__(self):
        dev = usb.core.find(idVendor=VID, idProduct=PID, backend=_BACKEND)
        if dev is None:
            raise RuntimeError(f"TURZX device {VID:04x}:{PID:04x} not found")
        self.dev = dev
        self.width = NATIVE_W
        self.height = NATIVE_H
        for iface in (0, 1):
            try:
                if dev.is_kernel_driver_active(iface):
                    dev.detach_kernel_driver(iface)
            except (NotImplementedError, usb.core.USBError):
                pass
        usb.util.claim_interface(dev, DATA_IFACE)

    def _w(self, data: bytes, timeout: int = 10000):
        self.dev.write(BULK_OUT, data, timeout=timeout)

    def cmd(self, c, x0=0, y0=0, x1=0, y1=0):
        b = bytearray(6)
        b[0] = x0 >> 2
        b[1] = ((x0 & 3) << 6) + (y0 >> 4)
        b[2] = ((y0 & 15) << 4) + (x1 >> 6)
        b[3] = ((x1 & 63) << 2) + (y1 >> 8)
        b[4] = y1 & 255
        b[5] = c
        self._w(bytes(b), timeout=2000)

    def init(self, brightness_param: int = 39):
        """Exact vendor power-on sequence captured from the Windows app."""
        self._w(bytes([0, 0, 0, 0, 0, 0xFF])); time.sleep(0.02)          # FF init
        self._w(bytes([0, 0, 0, 0, 0, 0x6E])); time.sleep(0.02)          # brightness 0
        self._w(bytes([0, 0, 0, 0, 0, 0x6D])); time.sleep(0.02)          # 6D
        self._w(bytes([0, 0, 0, 0, 0, 0x7A] + [0]*10)); time.sleep(0.02)  # 7A 16-byte
        self._w(bytes([0, 0, 0, 0, 0, 0x79, 0x64, 0x01, 0x40, 0x01, 0xE0] + [0]*5))
        time.sleep(0.02)                                                  # 79 portrait 320x480
        self.set_brightness(brightness_param); time.sleep(0.02)

    def set_brightness(self, param: int = 39):
        self.cmd(0x6E, x0=max(0, min(255, param)))

    def draw_bytes(self, data565: bytes, x0: int, y0: int, x1: int, y1: int):
        self.cmd(DISPLAY_BITMAP, x0, y0, x1, y1)
        time.sleep(0.002)
        self._w(data565)

    def draw(self, image: Image.Image, x: int = 0, y: int = 0):
        w = min(image.width, self.width - x)
        h = min(image.height, self.height - y)
        if (w, h) != image.size:
            image = image.crop((0, 0, w, h))
        self.draw_bytes(pixels.to_rgb565le(image), x, y, x + w - 1, y + h - 1)

    def solid(self, r, g, b):
        px = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        self.draw_bytes(px.to_bytes(2, "little") * (self.width * self.height),
                        0, 0, self.width - 1, self.height - 1)

    def close(self):
        try:
            usb.util.release_interface(self.dev, DATA_IFACE)
        except usb.core.USBError:
            pass
        usb.util.dispose_resources(self.dev)
