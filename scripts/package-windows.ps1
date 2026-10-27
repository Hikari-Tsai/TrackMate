# Build TrackMate for Windows with the engine next to TrackMate.exe and zip it into dist\.
# Usage: pwsh scripts/package-windows.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "== engine"
Push-Location "$Root/engine"
uv sync --group package
uv run --group package python packaging/build_engine.py
uv run python packaging/smoke_test.py dist/stem-engine/stem-engine.exe
Pop-Location

Write-Host "== app"
Push-Location "$Root/app"
flutter build windows --release
Pop-Location
$Out = "$Root/app/build/windows/x64/runner/Release"
if (Test-Path "$Out/engine") { Remove-Item -Recurse -Force "$Out/engine" }
Copy-Item -Recurse "$Root/engine/dist/stem-engine" "$Out/engine"
Copy-Item "$Root/LICENSE", "$Root/THIRD_PARTY_NOTICES.md" $Out

Write-Host "== archive"
New-Item -ItemType Directory -Force "$Root/dist" | Out-Null
$Zip = "$Root/dist/TrackMate-windows-x64.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path "$Out/*" -DestinationPath $Zip
Get-ChildItem "$Root/dist"
