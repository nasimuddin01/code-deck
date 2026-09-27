#!/usr/bin/env bash
# Build the downloadable macOS app: CODE DECK.app with Python, CODE DECK and
# libusb inside, wrapped in a DMG for GitHub Releases.
#
#   scripts/package-macos.sh              # this Mac's architecture
#   scripts/package-macos.sh --arch x86_64
#
# Needs: uv, node + pnpm, Homebrew libusb for the target architecture, and
# the Xcode Command Line Tools. Output: dist/release/CODE-DECK-<ver>-macos-<arch>.dmg
#
# The app is ad-hoc signed, not notarized (that needs a paid Apple Developer
# ID), so on first open macOS asks the user to allow it; README explains how.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

ARCH="$(uname -m)"
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
case "$ARCH" in arm64|aarch64) ARCH=arm64; PYARCH=aarch64 ;; x86_64) PYARCH=x86_64 ;; *) echo "arch?"; exit 2 ;; esac

VER="$(sed -n 's/^version = "\(.*\)"/\1/p' server/pyproject.toml)"
PYVER="3.13"
WORK="$ROOT/build/macos-$ARCH"
OUT="$ROOT/dist/release"
APP="$WORK/stage/CODE DECK.app"
say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

rm -rf "$WORK"; mkdir -p "$WORK/stage" "$OUT"

say "web app"
( cd web && pnpm install --frozen-lockfile --silent && pnpm build:server >/dev/null )

say "python package $VER"
( cd server && rm -rf dist && uv build --wheel -q )
WHEEL="$(ls server/dist/code_deck-*.whl)"

say "standalone python $PYVER ($PYARCH)"
REQ="cpython-$PYVER-macos-$PYARCH-none"
uv python install "$REQ" >/dev/null
PYBIN="$(uv python find "$REQ")"
PYROOT="$(cd "$(dirname "$PYBIN")/.." && pwd -P)"
cp -R "$PYROOT" "$WORK/python"
PY="$WORK/python/bin/python3"
rm -f "$WORK"/python/lib/python*/EXTERNALLY-MANAGED        # it's ours now

say "install CODE DECK into it"
uv pip install -q --python "$PY" "$WHEEL"

say "trim"
LIB="$(echo "$WORK"/python/lib/python3.*)"
rm -rf "$LIB"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3,pydoc_data} \
       "$LIB"/lib-dynload/_tkinter* "$WORK"/python/lib/{tcl,tk,itcl,thread}* \
       "$WORK"/python/share "$WORK"/python/include "$WORK"/python/bin/{idle*,pydoc*,2to3*}
find "$WORK/python" -name "__pycache__" -type d -prune -exec rm -rf {} +
"$PY" -m compileall -q -j 0 "$LIB" >/dev/null || true         # faster first start

say "libusb"
LIBUSB_DIR="$(brew --prefix libusb 2>/dev/null || true)"
DYLIB="$LIBUSB_DIR/lib/libusb-1.0.0.dylib"
[ -f "$DYLIB" ] || { echo "libusb not found for this architecture (brew install libusb)"; exit 1; }
if ! lipo -archs "$DYLIB" | grep -qw "$ARCH"; then
  echo "$DYLIB is $(lipo -archs "$DYLIB"), not $ARCH: build on a matching Mac or CI runner"; exit 1
fi
cp "$DYLIB" "$WORK/python/lib/libusb-1.0.dylib"
chmod u+w "$WORK/python/lib/libusb-1.0.dylib"
install_name_tool -id "@loader_path/libusb-1.0.dylib" "$WORK/python/lib/libusb-1.0.dylib"

say "menu bar app"
./menubar/build.sh >/dev/null
cp -R "menubar/dist/CODE DECK.app" "$APP"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$APP/Contents/Info.plist"
mv "$WORK/python" "$APP/Contents/Resources/python"
mkdir -p "$APP/Contents/Resources/licenses"
cp LICENSE "$APP/Contents/Resources/licenses/CODE-DECK-LICENSE.txt"
cp "$LIBUSB_DIR/COPYING" "$APP/Contents/Resources/licenses/libusb-LGPL-2.1.txt"
[ -f "$PYROOT/lib/python$PYVER/LICENSE.txt" ] && cp "$PYROOT/lib/python$PYVER/LICENSE.txt" "$APP/Contents/Resources/licenses/Python-LICENSE.txt"

say "sign (ad-hoc)"
# --deep doesn't reach loose Mach-O files under Resources, and Apple Silicon
# kills any process that loads code with a broken signature (install_name_tool
# above breaks libusb's), so sign every native library and binary explicitly
find "$APP/Contents/Resources/python" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) -print0 |
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then codesign --force --sign - "$f" 2>/dev/null; fi
  done
codesign --force --deep --sign - "$APP" 2>/dev/null
codesign --verify --deep --strict "$APP"

say "smoke test the bundled python"
# actually load libusb (a bad signature only shows up as a SIGKILL at load time)
"$APP/Contents/Resources/python/bin/python3" -c "import code_deck, usb, playwright, numpy, PIL, fastapi
from code_deck.turzx import libusb
libusb.backend()
from code_deck.turzx.usbraw import find_device
find_device()
print('code_deck', code_deck.__version__, '· libusb loads from', libusb.find_libusb())"

say "dmg"
ln -s /Applications "$WORK/stage/Applications"
cat > "$WORK/stage/Read me first.txt" <<TXT
CODE DECK $VER

1. Drag CODE DECK into Applications.
2. Open it from Applications. macOS will say it can't verify the app,
   because it isn't notarized by Apple. Click Done, then open
   System Settings > Privacy & Security, scroll down, and click
   "Open Anyway" next to CODE DECK. You only do this once.
3. The setup window opens. Plug in your TURZX screen and follow it.

Everything runs on your Mac; nothing is uploaded.
https://github.com/ehfazrezwan/code-deck
TXT
DMG="$OUT/CODE-DECK-$VER-macos-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "CODE DECK $VER" -srcfolder "$WORK/stage" -ov -format UDZO "$DMG"
( cd "$OUT" && shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256" )
say "done: $DMG ($(du -h "$DMG" | cut -f1))"
