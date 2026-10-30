# TrackMate (Flutter macOS front end)

TrackMate（中文：音軌助手）. Internal code names stay `stem_import` (Dart) and `stem_engine`
(Python); users never see them.

Drag stems in, check the Top-1 names, fix the ones flagged for review from the Top-5 menu
(or type a name), change category or colour, then preview and apply to the open Pro Tools
session. English UI, dark theme (`lib/ui/theme.dart`).

Design: Geist and Geist Mono type, layered zinc greys, 8 px corners and a periwinkle accent
(`lib/ui/theme.dart`). Fonts and icons are listed in the acknowledgements of the root README.
The work is done by the local engine (`../engine`), which the app starts as a child process.

## Run (development)

The Flutter SDK used during development lives in `../build/flutter-sdk` (stable 3.47.8).

```bash
F=../build/flutter-sdk/bin/flutter
$F run -d macos \
  --dart-define=ENGINE_CMD=$PWD/../engine/.venv/bin/stem-engine \
  --dart-define=ENGINE_HOME=$PWD/../build/engine_home
```

| dart-define | Meaning |
|---|---|
| `ENGINE_CMD` | engine executable to start (default `stem-engine` on PATH) |
| `ENGINE_ARGS` | extra engine arguments, space separated (`--no-download` is always passed: the models window starts the downloads) |
| `ENGINE_HOME` | `STEM_ENGINE_HOME` for the engine (models, aliases, caches) |
| `ENGINE_ATTACH` | path to `engine.json` of an engine already running; nothing is started |

The app is not sandboxed (`macos/Runner/*.entitlements`): it starts the engine and reads stems
from any folder.

## Structure

| File | Role |
|---|---|
| `macos/Runner/MainFlutterWindow.swift` | file drop on the whole window, open panel; channel `stem_import/native` |
| `lib/engine/engine_launcher.dart` | starts the engine, reads `{"port","token"}` from its first stdout line |
| `lib/engine/engine_api.dart` | HTTP client (`/analyze`, `/feedback`, `/apply`, …) |
| `lib/app_state.dart` | track list, two-pass analysis (text, then audio), edits, preview and apply |
| `lib/models.dart` | rows, candidates, catalog; `composeName` mirrors the engine's naming rule |
| `lib/ui/` | theme, header, track table, Top-5 menu (candidates, type a name, search, keep original), palette picker, apply dialogs |

Behaviour worth knowing:
- Adding files runs `/analyze` with `audio: none` first, then `audio: auto` only if some rows are
  still unsure; those rows show "Listening…" meanwhile.
- Choosing a candidate other than the engine's Top-1 calls `/feedback` with the name without
  the song title. DAW default names (`Audio 3`) are never learnt.
- "Type a name…" in the name menu sets a free name; it keeps the instrument and category and is
  not sent to `/feedback` (it is not an instrument choice). The name field itself is editable too.
- Changing the category recolours the row to the category colour unless a colour was picked.
- Rows with low or no confidence are highlighted until the user edits them.
- Scores are shown as whole percentages (menu and confidence column). They are the engine's raw
  scores, not calibrated probabilities: dictionary/spelling matches show 100 %, the text layer
  shows cosine similarity, the audio layer its probability among 16 classes (chance is 6 %).

## Tests

```bash
$F test                     # widget tests with a fake engine built from real engine output
$F test --update-goldens    # refresh test/goldens/track_list.png (screenshot)
```

`integration_test/real_flow_test.dart` drives the real app, engine and Pro Tools. Open a
**test** session first: the run adds folders and tracks to it.

```bash
$F test integration_test/real_flow_test.dart -d macos \
  --dart-define=ENGINE_CMD=$PWD/../engine/.venv/bin/stem-engine \
  --dart-define=ENGINE_HOME=<home with models> --dart-define=STEMS_DIR=$PWD/../build/m3_stems
```

`integration_test/real_tempo_test.dart` does the same for the tempo (detected on its own, chosen in
the step before the import, imported after the tracks). `STEMS_DIR`
holds rhythm stems with a known constant tempo, given as `TEMPO_BPM`; press **OK** in Pro Tools'
*MIDI Import Options* dialog when it appears (twice):

```bash
$F test integration_test/real_tempo_test.dart -d macos \
  --dart-define=ENGINE_CMD=$PWD/../engine/.venv/bin/stem-engine \
  --dart-define=ENGINE_HOME=<home with models> --dart-define=STEMS_DIR=<stems> --dart-define=TEMPO_BPM=85
```
