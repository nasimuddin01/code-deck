# TURZX 3.5-inch Windows USB protocol report

Captured 17 September 2026. Primary evidence is actual USBPcap traffic, not synthesized serial traces.

## Findings

The Windows app sends ordinary six-byte C5 rectangle commands followed by raw RGB565 little-endian pixels. Both complex full-frame payloads decode into clean 320x480 images without unescaping, decompression, or rearranging pixels. Across the two captures, all 851 bitmap rectangles have exactly width × height × 2 payload bytes; each rectangle's pixel data occupies one submitted URB. No bulk-IN data was observed.

The diagnostic brief's proposed nonstandard bitmap encoding is therefore **not supported by these captures**. The cause of corruption on the Mac remains unproven. Investigate transport completion, concurrent writes, pixel-buffer lifetime, and row stride against the included known-good payloads. The CDC line-coding behavior below is also a concrete difference to compare.

## Device, software, and capture method

- VID/PID: `1A86:5722`; serial string: `USB35INCHIPSV2`; Windows port: `COM5`.
- Driver: Microsoft `usbser`, INF `usbser.inf`, driver version `10.0.19041.3636`.
- App: `UsbMonitor.exe`, product Turzx, file/product version `2.2.1.0`, in `C:/Users/<user>/Downloads/35inchENG`.
- Capture: USBPcap 1.5.4.0; analysis/conversion: Wireshark 4.6.8. After reboot, the target appeared on USBPcap2, bus 2, device address 9. Bulk OUT endpoint is `0x03`; descriptor advertises 64-byte maximum bulk packets.
- USB device descriptor `bcdDevice=0x0100`. This is a USB device-release value, **not a verified firmware version**. Firmware version from the GUI was not obtained.
- Captured only address 9, with injected USB descriptors, 1,048,576-byte snap length and 16 MiB capture buffer. The raw PCAPs were converted losslessly to PCAPNG with editcap.
- Startup: capture began before launching the vendor app; 53.004154 seconds including initial idle time, 1,112 packets, 530 outgoing data submissions, 569,394 bulk-OUT payload bytes.
- Change: the user changed the background and pressed Run while recording; 115.159835 seconds including time waiting for that action, 2,420 packets, 1,184 outgoing data submissions, 904,278 bulk-OUT payload bytes. This is longer than the brief's suggested ten seconds so it includes the manual operation.
- Neither capture contains truncated packets or incomplete bitmap transactions. Every captured outgoing bulk submission has a matching successful completion. There are two canceled zero-payload input requests during initialization in each capture. The collector was stopped after its stdin quit request did not exit promptly; both files parse completely. No drop counter is available, so zero capture loss is not asserted.

## A. Initialization

Times below are seconds from the start of `turzx_startup.pcapng`; the first six packets are injected descriptors at time zero.

| Packet | Time (s) | OUT bytes | Interpretation |
|---|---:|---|---|
| 53 | 15.646108 | `00 00 00 00 00 ff` | Initialization command FF; exact firmware semantics unverified |
| 55 | 15.663706 | `00 00 00 00 00 6e` | Brightness command, value 0 |
| 57 | 15.664201 | `00 00 00 00 00 6d` | Command 6D, observed during startup |
| 59 | 15.786075 | `00 00 00 00 00 7a 00 00 00 00 00 00 00 00 00 00` | 16-byte setting command, value 0 |
| 61 | 15.800913 | `00 00 00 00 00 79 64 01 40 01 e0 00 00 00 00 00` | Portrait orientation, 320 × 480 |
| 63 | 16.327983 | `09 c0 00 00 00 6e` | Brightness parameter 39 |
| 65 | 16.328993 | `00 00 04 fd df c5` | Full rectangle (0,0) through (319,479), inclusive |
| 67 | 16.329194 | 307,200 pixel bytes | Full frame |

No command ending `65` (reset 101) was observed. The same initialization sequence appears when the user presses Run in the change capture. The timestamped first 256 bulk-OUT bytes, including the beginning of pixel data, are in `startup-first-256-bytes.txt`.

### CDC serial setup — noteworthy

The vendor code creates a serial port at 115200, 8 data bits, no parity, one stop bit, DTR and RTS enabled. USB evidence shows more detail:

- GET_LINE_CODING replies are `00 00 00 06 00 00 08`: little-endian rate `0x06000000` (100,663,296), 8N1. Do not assume this represents an actual physical UART rate.
- SET_LINE_CODING at packets 27 and 41 writes `00 c2 01 00 00 00 08` (115200, 8N1).
- Subsequent SET_LINE_CODING at packets 33 and 47 writes back `00 00 00 06 00 00 08`.
- SET_CONTROL_LINE_STATE progresses through values 0, 2, and 3; final value 3 enables both DTR and RTS.

`startup-control-requests.txt` records setup bytes and attached data with timestamps. These are control transfers, not application bitmap headers or pixel data. Their causal role in the Mac issue has not been tested.

## B. Bitmap framing

Each bitmap begins with six packed-coordinate bytes, ending in `C5`. There is no separate length prefix in the captured bitmap path. For header bytes b0…b5:

```text
x0 = (b0 << 2) | (b1 >> 6)
y0 = ((b1 & 63) << 4) | (b2 >> 4)
x1 = ((b2 & 15) << 6) | (b3 >> 2)
y1 = ((b3 & 3) << 8) | b4
payload_length = (x1-x0+1) * (y1-y0+1) * 2
```

The full-frame header is `00 00 04 fd df c5`. Most subsequent updates are small rectangles rather than entire screens. The detailed rectangle list and size checks are included in each `*-analysis.json` file.

## C. Payload encoding

Raw RGB565LE: `pixel = low_byte | (high_byte << 8)`, red in bits 15…11, green in 10…5, blue in 4…0. Rows run left-to-right, then top-to-bottom in the decoded portrait image.

Direct decoding of both 307,200-byte full-frame payloads produces the original and changed backgrounds cleanly. No bytes were removed, inserted, or interpreted as compression headers. All rectangle lengths match raw RGB565 exactly. The first full-frame payload begins `b1 2a 90 22 90 22 90 22 f1 42 51 53 31 4b 31 4b`. A later white region includes repeated `ff ff` pixels. Incidental occurrences of zlib/JPEG magic inside pixel data would not establish compression.

A dedicated solid-color vendor theme was not captured; the exact byte counts and successful direct decoding of two complex frames provide stronger evidence for this observed path. `*-frame.rgb565le` contains each full-frame payload unchanged; `*-decoded.png` is its reconstructed image. These PNGs are **not photographs of the physical screen**.

## D. Chunking and pacing

| Measurement | Startup | Background change |
|---|---:|---:|
| Bitmap rectangles | 262 | 589 |
| Full-frame pixel URB | 307,200 bytes | 307,200 bytes |
| Full-frame submit → completion | 1.849429 s | 1.838501 s |
| C5 header → pixel submit, median | 202.5 µs | 240 µs |
| C5 header → pixel submit, range | 71–573 µs | 72–540 µs |
| Most common smaller pixel URB | 504 bytes (182 times) | 504 bytes (403 times) |
| Next common small payload | 1,232 bytes (18 times) | 1,232 bytes (51 times) |

The startup full-frame header and pixels are packets 65 and 67, separated by 201 µs; completion is packet 68. This is a single large URB at the host capture level. The USB endpoint's 64-byte packet size does not mean the app issues 64-byte writes. USBPcap exposes URBs, not every physical bus transaction.

Do not infer that the device accepts a full frame instantaneously: the pixel transfer takes about 1.84 seconds to complete. A Mac comparison should serialize each header/payload pair and wait for actual write completion/draining before issuing subsequent commands. This is a test recommendation, not a confirmed fix.

## E. Device-to-host traffic

No nonempty bulk-IN payload was recorded in either capture. There is consequently no observed application ACK byte between bitmap chunks. CDC control replies exist, including the seven-byte line-coding response above. Successful host OUT completions are not device application ACK messages; physical USB handshakes are below this capture level.

## F. Orientation

The exact 16-byte frame is:

```text
00 00 00 00 00 79 64 01 40 01 e0 00 00 00 00 00
```

Byte 5 is `79`. Byte 6 is `64` = 100 + rotation 0. Bytes 7–8 are `01 40` = 320; bytes 9–10 are `01 e0` = 480, both dimensions big-endian. Stored `rotation` was 0 before and after testing; no orientation change was necessary.

## GUI recovery and settings

The app's `config/AppConfig.data` is a .NET binary-serialized configuration. Its `autoRun=true` path explicitly places the window off-screen and subsequently minimizes/hides it. After backing up the file, changing only this setting to false and restarting the app restored a visible main window. The user's subsequent background change was retained. Current theme name is `3.5inchTheme1`, brightness parameter 39, rotation 0, and autoRun false. Re-enabling automatic startup may restore the previous hidden-window behavior.

The backup is retained in the task's `work/AppConfig.before-gui-fix.data`; avoid restoring the whole file casually because it predates the user's later theme changes. The vendor executable was not patched. The app self-elevates to administrator; the UI helper could not read its elevated controls, so the user performed the background change.

`vendor-file-inventory.txt` lists EXE/DLL/INI/TXT files. Themes are under `config/*.data`, backgrounds under `3.5`, with additional `Driver`, `config/statusbar`, and `logs` directories. No firmware update was attempted.

## Deliverables and remaining handoff

Both requested PCAPNG files, transfer CSVs, raw full-frame fixtures, decoded images, and supporting analyses are included in `turzx-diagnostics.zip`. The earlier `*_serial.*` files are fallback application-level traces and are not needed to interpret the real USB captures.

Still external to this report: a phone photo of the physical screen, and copying the deliverables into `~/Projects/code-display/` on the Mac. No Mac connection/destination was supplied, so no transfer has been performed. The actual Mac rendering bug has not been fixed or reproduced here.

## Rechecking in Wireshark

```text
usb.device_address == 9 && usb.transfer_type == 3
```

For outgoing payload submissions add `usb.endpoint_address == 0x03 && usb.data_len > 0`. Packet 67 in each original full capture contains the full-frame data. Wireshark decodes it as USB Communications/CDC, so inspect its OUT payload rather than assuming the generic `usb.capdata` field is populated. Captured packet numbers in this report refer to the included untrimmed files.
