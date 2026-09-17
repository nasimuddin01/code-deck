#!/usr/bin/env bash
# Regenerate the app icon (.icns) and the menu bar template glyph from the
# SVGs. Needs rsvg-convert (brew install librsvg) and iconutil (macOS).
# Output goes to icon/out/ (gitignored); build.sh copies it into the bundle.
set -euo pipefail
cd "$(dirname "$0")"
command -v rsvg-convert >/dev/null || { echo "rsvg-convert missing: brew install librsvg" >&2; exit 1; }

rm -rf out icon.iconset
mkdir -p out icon.iconset
for s in 16 32 128 256 512; do
  rsvg-convert -w $s -h $s logo.svg -o "icon.iconset/icon_${s}x${s}.png"
  rsvg-convert -w $((s*2)) -h $((s*2)) logo.svg -o "icon.iconset/icon_${s}x${s}@2x.png"
done
iconutil -c icns icon.iconset -o out/icon.icns
rsvg-convert -w 512 -h 512 logo.svg -o out/icon.png
rsvg-convert -w 18 -h 18 menubar-icon.svg -o out/MenuBarIcon.png
rsvg-convert -w 36 -h 36 menubar-icon.svg -o out/MenuBarIcon@2x.png
rm -rf icon.iconset
echo "icons -> $(pwd)/out"
