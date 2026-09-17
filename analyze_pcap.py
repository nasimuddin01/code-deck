"""Analyze a USBPcap capture of the TURZX vendor software.

Usage: .venv/bin/python analyze_pcap.py turzx_startup.pcapng

Dumps: bulk OUT transfer sizes + inter-transfer gaps, detected 6-byte command
frames (rev-A packing), payload runs between commands, and device->host traffic.
"""
import json
import subprocess
import sys
from collections import Counter

CMDS = {101: "RESET", 102: "CLEAR", 108: "SCREEN_OFF", 109: "SCREEN_ON",
        110: "BRIGHTNESS", 121: "ORIENTATION", 122: "MIRROR",
        130: "?130", 131: "?131", 161: "?161", 162: "?162", 164: "?164",
        166: "?166", 169: "?169", 180: "?180", 194: "BITMAP_194",
        195: "PIXELS_195", 196: "?196", 197: "BITMAP_197", 198: "BITMAP_198",
        201: "?201", 212: "?212", 69: "HELLO"}


def tshark_json(path):
    out = subprocess.run(
        ["tshark", "-r", path, "-Y", "usb.transfer_type == 3",  # bulk
         "-T", "json", "-e", "frame.time_relative", "-e", "usb.endpoint_address.direction",
         "-e", "usb.capdata", "-e", "usb.data_len", "--no-duplicate-keys"],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def main(path):
    rows = []
    for pkt in tshark_json(path):
        f = pkt["_source"]["layers"]
        t = float(f["frame.time_relative"][0])
        direction = f.get("usb.endpoint_address.direction", ["?"])[0]
        data = f.get("usb.capdata", [None])[0]
        if data:
            rows.append((t, "OUT" if direction == "0" else "IN", bytes.fromhex(data.replace(":", ""))))

    print(f"{len(rows)} bulk data transfers")
    ins = [r for r in rows if r[1] == "IN"]
    print(f"device->host transfers: {len(ins)}")
    for t, _, d in ins[:10]:
        print(f"  IN t={t:.3f} len={len(d)} hex={d[:16].hex()}")

    outs = [r for r in rows if r[1] == "OUT"]
    sizes = Counter(len(d) for _, _, d in outs)
    print(f"\nOUT size histogram (top 10): {sizes.most_common(10)}")

    # gaps between consecutive OUT transfers
    gaps = [(outs[i + 1][0] - outs[i][0]) for i in range(len(outs) - 1)]
    big = [(outs[i + 1][0], g) for i, g in enumerate(gaps) if g > 0.005]
    print(f"gaps >5ms: {len(big)} (first 15): {[(round(t,3), round(g*1000,1)) for t, g in big[:15]]}")

    # command frame detection: 6-byte OUT transfers, or 6-byte prefix
    print("\ncommand log (6-byte transfers):")
    payload_run = 0
    for t, _, d in outs:
        if len(d) == 6 and d[5] in CMDS:
            if payload_run:
                print(f"    ... payload {payload_run} bytes")
                payload_run = 0
            x = (d[0] << 2) | (d[1] >> 6)
            y = ((d[1] & 0x3F) << 4) | (d[2] >> 4)
            ex = ((d[2] & 0xF) << 6) | (d[3] >> 2)
            ey = ((d[3] & 3) << 8) | d[4]
            print(f"  t={t:8.3f} {CMDS[d[5]]:14s} ({x},{y})-({ex},{ey})  raw={d.hex()}")
        elif len(d) == 16 and d[5] in CMDS:
            print(f"  t={t:8.3f} {CMDS[d[5]]:14s} 16-byte  raw={d.hex()}")
        else:
            payload_run += len(d)
    if payload_run:
        print(f"    ... payload {payload_run} bytes")


if __name__ == "__main__":
    main(sys.argv[1])
