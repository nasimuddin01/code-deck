# TURZX 3.5" USB screen — Windows USB capture brief

## Context (read first)
This display is a Turing Smart Screen rev A protocol clone (USB serial device,
serial number string `USB35INCHIPSV2`, shows up as a COM port). On macOS we
drive it with the documented rev A protocol: 6-byte command frames, then raw
RGB565 little-endian pixels after a DISPLAY_BITMAP (0xC5) command,
320x480 portrait.

Confirmed working from the Mac: solid-color frames and sparse test patterns
render pixel-perfect (byte order, geometry, timing, data integrity all good).
Confirmed broken: any complex frame (antialiased dashboard) renders as
sheared/stripey noise. Byte-value toxicity was ruled out (a frame stripped of
all protocol command byte values still fails). Conclusion: the vendor protocol
must differ from stock rev A in some way we can only see on the wire —
possibly escaping/byte-stuffing, a length-prefixed or chunk-acknowledged
bitmap mode, a different init sequence, or compression.

## Your mission
Capture the USB traffic of the official TURZX Windows software driving this
screen, and report the protocol details below. The capture file itself is the
primary deliverable.

## Steps

1. **Identify the device.** Plug in the screen. Device Manager -> Ports (COM & LPT)
   -> the new COM port -> Properties -> Details -> Hardware IDs. Record VID, PID,
   and the COM number. Also note the driver name (usbser.sys or vendor driver).

2. **Install Wireshark with USBPcap** (check the USBPcap component during
   install; reboot if prompted).

3. **Capture the app startup.** Vendor software NOT running yet. Start a
   Wireshark capture on the USBPcap interface for the root hub that hosts the
   device (USBPcapCMD lists devices per hub; pick the one showing the COM
   device). Then launch the TURZX software and let it drive the screen for
   about 30 seconds (it should show its theme/dashboard). Stop the capture.
   Save as `turzx_startup.pcapng`.

4. **Capture a content change** (second, short capture): with software running,
   change something visual (theme, background, brightness), ~10 s.
   Save as `turzx_change.pcapng`.

5. **If the app allows a solid background/theme, set one** before the second
   capture. A solid-color frame makes the payload encoding obvious (raw RGB565
   = one repeating 2-byte pattern; escaping/compression = visibly not that).

6. **Poke the vendor app folder** (usually under Program Files or wherever it
   installed): list exe/dll names, any config files with device settings
   (rotation!), any firmware version shown in the app UI. If there is a
   rotation/orientation setting, set it to portrait/0 and note what it was.

## Analysis to include in your report

Filter to bulk OUT traffic to the device (URB_BULK out, the device address you
identified). Then answer:

- **A. Init sequence**: hex dump of the first ~256 bytes the app sends after
  connect, with timestamps. Do you see 6-byte frames ending in bytes like
  0x65 (101, reset), 0x6D/0x6E, 0x79 (121, orientation), 0xC5 (197, display
  bitmap)? Or something else entirely?
- **B. Bitmap framing**: the bytes immediately before each large data burst.
  Is it a 6-byte frame ending 0xC5? Different length? Any length prefix?
- **C. Payload encoding**: inside a large burst, is it raw RGB565LE? (For a
  solid region you'd see one 2-byte pattern repeating.) Any escape bytes
  inserted around specific values? Any zlib/JPEG magic (78 9C / FF D8)?
- **D. Chunking + pacing**: typical URB transfer sizes for pixel data, and the
  time gaps between them (pcap timestamps). Total bytes per full frame
  (320*480*2 = 307,200 raw)?
- **E. Device->host traffic**: ANY bulk IN data from the device during
  streaming? (ACK bytes between chunks would be a protocol we're missing.)
- **F. Orientation**: any 16-byte frame with byte[5]=0x79? Record it fully.

## Deliverables
1. `turzx_startup.pcapng` and `turzx_change.pcapng` (copy both to the Mac,
   drop them into ~/Projects/code-display/).
2. A text report answering A-F plus: VID/PID, COM number, driver, app name +
   version, firmware version if shown, rotation setting found.
3. One phone photo of the screen while vendor software drives it (proves the
   hardware renders complex content cleanly).

If USBPcap shows nothing (some vendor drivers bypass usbser), fall back to
capturing serial writes with API Monitor (hook WriteFile on the app process,
log first bytes of each write + sizes + timing) and report the same A-F.
