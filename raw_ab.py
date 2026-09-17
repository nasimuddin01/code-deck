"""Decisive A/B: isolate serial flow-control / raw-tty as the corruption cause.

Both variants send the SAME 307200-byte payload as ONE write (Windows-style).
Only difference:
  A  -> rtscts OFF, DTR/RTS asserted high, full cfmakeraw tty  (matches Windows)
  B  -> rtscts ON (hardware handshake) -- the old Mac config
If A is clean and B is stripey, flow control was the bug.
The card has a diagonal + numbered gridlines + full gradient so shear is obvious.
"""
import sys, time, termios
import numpy as np
import serial
from PIL import Image, ImageDraw, ImageFont

PORT = "/dev/cu.usbmodemUSB35INCHIPSV21"
W, H = 320, 480
DISPLAY_BITMAP = 197

def font(sz):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", sz)
    except Exception:
        return ImageFont.load_default()

def card(label):
    img = Image.new("RGB", (W, H), (12, 12, 16))
    d = ImageDraw.Draw(img)
    # full-range vertical gradient strip on the right (guarantees every byte value)
    for y in range(H):
        c = int(255 * y / (H - 1))
        d.line([(W - 40, y), (W - 1, y)], fill=(c, 255 - c, (c * 2) % 256))
    # numbered horizontal gridlines every 40 px
    f = font(16)
    for y in range(0, H, 40):
        d.line([(0, y), (W - 44, y)], fill=(70, 70, 80))
        d.text((4, y + 2), f"y={y}", font=f, fill=(200, 200, 210))
    # bright diagonals: a clean straight line if no shear
    d.line([(0, 0), (W - 1, H - 1)], fill=(0, 240, 255), width=2)
    d.line([(0, H - 1), (W - 1, 0)], fill=(255, 120, 0), width=2)
    # big label
    d.rectangle([70, 200, 250, 280], fill=(0, 0, 0))
    d.text((84, 214), label, font=font(52), fill=(255, 255, 255))
    return img

def to565(img):
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    r, g, b = a[..., 0] >> 3, a[..., 1] >> 2, a[..., 2] >> 3
    return ((r << 11) | (g << 5) | b).astype("<u2").tobytes()

def make_raw(fd):
    at = termios.tcgetattr(fd)
    at[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
               termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON | termios.IXOFF)
    try: at[0] &= ~termios.IXANY
    except AttributeError: pass
    at[1] &= ~termios.OPOST
    at[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
    at[2] &= ~(termios.CSIZE | termios.PARENB)
    at[2] |= termios.CS8
    termios.tcsetattr(fd, termios.TCSANOW, at)

def cmd(ser, c, x0, y0, x1, y1):
    b = bytearray(6)
    b[0] = x0 >> 2
    b[1] = ((x0 & 3) << 6) + (y0 >> 4)
    b[2] = ((y0 & 15) << 4) + (x1 >> 6)
    b[3] = ((x1 & 63) << 2) + (y1 >> 8)
    b[4] = y1 & 255
    b[5] = c
    ser.write(bytes(b)); ser.flush()

def send(rtscts, label):
    ser = serial.Serial(PORT, 115200, timeout=1, rtscts=rtscts)
    ser.dtr = True; ser.rts = True
    make_raw(ser.fd)               # full raw tty for BOTH variants
    time.sleep(1.5)                # DTR settle
    ser.reset_input_buffer(); ser.reset_output_buffer()
    data = to565(card(label))
    cmd(ser, DISPLAY_BITMAP, 0, 0, W - 1, H - 1)
    time.sleep(0.02)
    ser.write(data)                # single Windows-style write
    ser.flush()
    time.sleep(0.05)
    ser.close()

if __name__ == "__main__":
    print("A = NO flow control (Windows-match) | B = RTSCTS handshake (old). Ctrl-C to stop.", flush=True)
    while True:
        send(False, "A"); print("shown A (no-flow) ...", flush=True); time.sleep(12)
        send(True,  "B"); print("shown B (rtscts) ...", flush=True); time.sleep(12)
