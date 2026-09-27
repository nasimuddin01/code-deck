#!/usr/bin/env bash
# Build the CODE DECK menu bar app with swiftc (Xcode Command Line Tools are
# enough). Produces dist/CODE DECK.app, universal, ad-hoc signed.
#
#   ./build.sh            build
#   ./build.sh --install  build, copy to ~/Applications, start at login, open
#   ./build.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"

APP="dist/CODE DECK.app"
BIN_NAME="CodeDeckMenuBar"
LABEL="com.codedeck.menubar"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
INSTALLED="$HOME/Applications/CODE DECK.app"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$AGENT"
  pkill -x "$BIN_NAME" 2>/dev/null || true
  rm -rf "$INSTALLED"
  echo "removed $INSTALLED and its login item"
  exit 0
fi

rm -rf "$APP" dist/obj
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" dist/obj

common=(-O -swift-version 5 -framework Cocoa -framework WebKit -framework Carbon Sources/main.swift)
swiftc "${common[@]}" -target arm64-apple-macosx13.0  -o "dist/obj/$BIN_NAME-arm64"
swiftc "${common[@]}" -target x86_64-apple-macosx13.0 -o "dist/obj/$BIN_NAME-x86_64"
lipo -create "dist/obj/$BIN_NAME-arm64" "dist/obj/$BIN_NAME-x86_64" -output "$APP/Contents/MacOS/$BIN_NAME"
cp Info.plist "$APP/Contents/Info.plist"
# app icon + menu bar glyph (regenerated from SVG when rsvg-convert is around)
if [[ ! -f icon/out/icon.icns ]] && command -v rsvg-convert >/dev/null; then ./icon/make.sh >/dev/null; fi
if [[ -f icon/out/icon.icns ]]; then
  cp icon/out/icon.icns icon/out/MenuBarIcon.png icon/out/MenuBarIcon@2x.png "$APP/Contents/Resources/"
else
  echo "note: no icon (brew install librsvg, then ./icon/make.sh)"
fi
codesign --force --sign - "$APP" >/dev/null
echo "built $APP ($(lipo -archs "$APP/Contents/MacOS/$BIN_NAME"))"

if [[ "${1:-}" == "--install" ]]; then
  pkill -x "$BIN_NAME" 2>/dev/null || true
  mkdir -p "$HOME/Applications"
  rm -rf "$INSTALLED"
  cp -R "$APP" "$INSTALLED"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$INSTALLED/Contents/MacOS/$BIN_NAME</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Interactive</string>
</dict></plist>
EOF
  # bootout is asynchronous: bootstrapping before the old job is gone fails
  # with "Bootstrap failed: 5: Input/output error", so wait, then retry
  for _ in $(seq 1 40); do
    launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || break
    sleep 0.25
  done
  for attempt in 1 2 3 4 5; do
    launchctl bootstrap "gui/$(id -u)" "$AGENT" 2>/dev/null && break
    [ "$attempt" = 5 ] && { echo "launchctl bootstrap failed; open \"$INSTALLED\" by hand" >&2; exit 1; }
    sleep 1
  done
  echo "installed $INSTALLED — running, starts at login"
fi
