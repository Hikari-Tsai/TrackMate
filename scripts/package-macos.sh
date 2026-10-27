#!/usr/bin/env bash
# Build TrackMate.app with the engine inside, ad-hoc signed, and pack it as .zip and .dmg in dist/.
# Usage: scripts/package-macos.sh   (FLUTTER=/path/to/flutter to use another Flutter)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLUTTER="${FLUTTER:-flutter}"
ARCH="$(uname -m)"

echo "== engine"
cd "$ROOT/engine"
uv sync --group package
uv run --group package python packaging/build_engine.py
uv run python packaging/smoke_test.py dist/stem-engine/stem-engine

echo "== app"
cd "$ROOT/app"
"$FLUTTER" build macos --release
APP="$ROOT/app/build/macos/Build/Products/Release/TrackMate.app"
rm -rf "$APP/Contents/Resources/engine"
cp -R "$ROOT/engine/dist/stem-engine" "$APP/Contents/Resources/engine"
# The bundle changed after Flutter signed it: sign again (ad hoc, no Developer ID).
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "== archives"
mkdir -p "$ROOT/dist"
rm -f "$ROOT/dist/TrackMate-macos-$ARCH".{zip,dmg}
ditto -c -k --keepParent "$APP" "$ROOT/dist/TrackMate-macos-$ARCH.zip"
hdiutil create -volname TrackMate -srcfolder "$APP" -ov -format UDZO "$ROOT/dist/TrackMate-macos-$ARCH.dmg" >/dev/null
ls -lh "$ROOT/dist"
