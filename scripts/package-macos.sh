#!/usr/bin/env bash
# Build a universal TrackMate.app (Apple Silicon and Intel) with both engines inside, ad-hoc
# signed, and pack it as .zip and a drag-to-install .dmg in dist/. The x86_64 engine is built
# with an x86_64 Python under Rosetta 2, so this runs on an Apple Silicon Mac.
# Usage: scripts/package-macos.sh   (FLUTTER=/path/to/flutter to use another Flutter)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLUTTER="${FLUTTER:-flutter}"

echo "== engine (arm64)"
cd "$ROOT/engine"
uv sync --group package
uv run --group package python packaging/build_engine.py --dist dist/arm64
uv run python packaging/smoke_test.py dist/arm64/stem-engine/stem-engine

echo "== engine (x86_64, Rosetta 2)"
UV_PROJECT_ENVIRONMENT=.venv-x86_64 uv sync --group package --python cpython-3.12-macos-x86_64-none
.venv-x86_64/bin/python packaging/build_engine.py --dist dist/x86_64
.venv-x86_64/bin/python packaging/smoke_test.py dist/x86_64/stem-engine/stem-engine
for arch in arm64 x86_64; do
  [ "$(lipo -archs "dist/$arch/stem-engine/stem-engine")" = "$arch" ] || { echo "engine is not $arch"; exit 1; }
done

echo "== app"
cd "$ROOT/app"
"$FLUTTER" build macos --release
APP="$ROOT/app/build/macos/Build/Products/Release/TrackMate.app"
for arch in arm64 x86_64; do lipo "$APP/Contents/MacOS/TrackMate" -verify_arch "$arch"; done
rm -rf "$APP/Contents/Resources/engine"
mkdir -p "$APP/Contents/Resources/engine"
for arch in arm64 x86_64; do
  cp -R "$ROOT/engine/dist/$arch/stem-engine" "$APP/Contents/Resources/engine/$arch"
done
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$APP/Contents/Resources/"
# The bundle changed after Flutter signed it: sign again (ad hoc, no Developer ID).
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "== archives"
mkdir -p "$ROOT/dist"
rm -f "$ROOT/dist"/TrackMate-macos-*.{zip,dmg}
ditto -c -k --keepParent "$APP" "$ROOT/dist/TrackMate-macos-universal.zip"
# Drag-to-install window: the app, an arrow and an Applications shortcut (scripts/dmg).
uvx --from dmgbuild==1.6.7 dmgbuild -s "$ROOT/scripts/dmg/settings.py" -D app="$APP" \
  -D background="$ROOT/scripts/dmg/background.png" TrackMate "$ROOT/dist/TrackMate-macos-universal.dmg" >/dev/null
ls -lh "$ROOT/dist"
