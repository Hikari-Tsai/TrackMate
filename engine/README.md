# TrackMate engine

Local engine of TrackMate (音軌助手): recognises instruments from track names and audio
(layers A–D, see the repository README), analyses stereo files, downloads its models and
serves an HTTP API to the macOS front end.

## Run

```bash
uv sync --group dev
uv run stem-engine            # prints {"port": ..., "token": ...}; starts model downloads (--no-download: the app does)
uv run pytest                 # 60 tests; the full-engine test needs downloaded models
```

State lives in `~/Library/Application Support/TrackMate` (override with `STEM_ENGINE_HOME`):
`models/` (verified downloads), `cache/` (C-layer index vectors), `user_aliases.json`
(corrections from `/feedback`), `engine.json` (port and token, mode 0600).

## Layout

| Module | Role |
|---|---|
| `names.py` | clean-up, tokens, batch prefix/suffix removal, DAW default names |
| `kb.py` | `kb/mix_naming.json` + user aliases |
| `textmatch.py` | layer A (dictionary, modifiers, number, ambiguous terms) and B (fuzzy) |
| `embed.py` | layer C: Qwen3-Embedding ONNX, NONE anchors, cached index |
| `audio.py` | layer D: PE-AV audio ONNX, loudest segments, `data/peav_prototypes.npz` |
| `pipeline.py` | merge into Top-1 + Top-5, confidence, proposed name, colour, folder |
| `stereo.py` | wraps `stereo_analysis/stereo_analyzer.py` |
| `models.py` | pinned, resumable, SHA-256-checked downloads (`data/model_manifest.json`) |
| `protools.py` | PTSL access with the M0 workarounds (import, rename, colour, folders) |
| `apply.py` | `/apply`: plan (unique names, folders) and execution with verification |
| `tempo.py` | `/tempo`: Beat This! (ONNX) on the rhythm stems, constant BPM or tempo map, tempo-only MIDI, import and check in Pro Tools |
| `api.py` | FastAPI; 127.0.0.1 only, bearer token, local Host header |

## API

All endpoints except `/health` need `Authorization: Bearer <token>`.

| Endpoint | |
|---|---|
| `GET /health` | liveness |
| `GET /models`, `POST /models/download` | per model: `state`, `progress`, `size`, `bytes_done`, `on_disk`, `current_file`, `error`; which layers are active; `dir` |
| `DELETE /models` | deletes every downloaded model file → `freed_bytes`; 409 `models_downloading` while a download runs |
| `POST /analyze` | `{"files": [...], "audio": "none" \| "auto" \| "all", "stereo": true}` |
| `POST /feedback` | `{"name": "Gtr Fuzz", "instrument": "electric_guitar"}` → user alias |
| `GET /instruments`, `GET /categories` | lists for the dropdown search and the settings page |
| `GET /session` | Pro Tools session and tracks over PTSL |
| `POST /apply` | `{"tracks": [{file, name, category, color_index?, folder?, mono}], "dry_run": false}` |
| `POST /tempo` | `{"tracks": [{file, category}]}` → `bpm`, `bpm_rounded`, `bpm_min`/`bpm_max` (per bar), `steady`, `suggested_mode`, `signature_beats`, `beats`, `downbeats`, `sources` |
| `POST /tempo/apply` | `{beats, downbeats, duration, mode: "constant" \| "variable", bpm?, factor: 0.5 \| 1 \| 2, signature_beats?, folder?, import_to_pro_tools}` → `midi_path`, `imported`, `applied` |

`/apply` creates (or reuses) one Basic Folder per category in the order of `categories.json`,
imports each file after the previous track (ConvertAudio; mono first when `mono` is true and the
stereo analysis recommends it), renames each new track by ID to a name made unique beforehand,
colours folders and tracks, then re-reads the session and reports `name_ok`, `folder_ok` and
`color_ok` per track. `dry_run` returns the plan for the preview without touching Pro Tools.

`/tempo` mixes the drum and percussion stems (else bass, guitars, keys and synths, else all
stems) to mono at 22.05 kHz, runs Beat This! and cleans the beats against the median beat gap
(double-time passages dropped, pauses filled). `steady` means every beat lies within 30 ms of
one straight grid; the app then suggests a constant tempo. `/tempo/apply` writes a tempo-only
MIDI file (one tempo, or one tempo per bar so each bar line falls on its detected downbeat),
imports it through PTSL (Pro Tools shows its MIDI Import Options dialog; the call returns when
the user closes it) and reads a Bars|Beats position back to check that the tempo changed:
`applied` is false when the dialog was cancelled.

`audio: "auto"` runs layer D only for tracks the text layers could not settle; the front end
can first call with `"none"` for an instant result and then with `"auto"`.

## Tools

- `tools/eval_text.py [--sweep]`: text layers on `experiments/c_layer_embedding/testset_realistic.json`
- `tools/eval_audio.py [N]`: layer D on Medley-solos-DB test clips
- `tools/build_peav_prototypes.py`: rebuild D-layer prototypes with the PyTorch text encoder
- `tools/e2e_apply.py STEMS_DIR [HOME]`: analyze → dry run → apply → session, against a running engine and Pro Tools (use a test session)
