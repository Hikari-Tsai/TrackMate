"""M0-a technical check: PTSL connection, audio import, track creation and rename.

Runs against the Pro Tools that is open on this Mac (PTSL on localhost:31416). Every step
that changes a session runs only in a dedicated test session (TEST_SESSION). When no
session is open, the script creates it; when another session is open, it only reads
session information and stops before changing anything.

Each step is timed and logged to results/m0_<time>.json.

Usage:
  python m0_probe.py info                 read-only: version, session, tracks, colour palette
  python m0_probe.py run-all STEMS_DIR    full check in the test session
"""
from __future__ import annotations

import datetime
import json
import pathlib
import shutil
import sys
import time
import traceback

import ptsl
from google.protobuf import json_format
from ptsl import PTSL_pb2 as pt
from ptsl.ops import Operation

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEST_SESSION = "M0_PTSL_Test"
SESSION_DIR = ROOT / "build" / "m0_session"
COMPANY, APP = "ITRI", "Stem Import M0"


# Commands in PTSL.proto that py-ptsl 602 does not wrap yet. Operation derives the command
# ID and the request/response types from the class name.
class DropEmptyLists(Operation):
    # py-ptsl serialises every field, so unset repeated fields go out as []. Pro Tools then
    # rejects requests that accept either track_ids or track_names ("Only one ... must be
    # defined"), so empty lists are removed before sending.
    def json_messup(self, in_json: str) -> str:
        body = json.loads(in_json)
        return json.dumps({k: v for k, v in body.items() if v != []})


class CId_GetColorPalette(Operation):
    pass


class CId_SetTrackColor(DropEmptyLists):
    pass


class CId_DeleteTracks(DropEmptyLists):
    pass


class CId_Import(Operation):
    # Own wrapper: py-ptsl 602 Engine.import_audio sends import_type=1, which is
    # IType_Session in this proto; audio import needs IType_Audio (2).
    pass


class Log:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def step(self, name: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        rec = {"step": name}
        try:
            out = fn(*args, **kwargs)
            rec.update(ok=True, result=out)
        except Exception as exc:  # record and continue; M0 wants every result
            out = None
            rec.update(ok=False, error=f"{type(exc).__name__}: {exc}",
                       trace=traceback.format_exc(limit=3))
        rec["seconds"] = round(time.perf_counter() - t0, 3)
        self.steps.append(rec)
        status = "OK " if rec["ok"] else "ERR"
        detail = rec.get("error") or json.dumps(rec.get("result"), ensure_ascii=False, default=str)[:300]
        print(f"[{status}] {name} ({rec['seconds']} s) {detail}", flush=True)
        return out

    def save(self) -> pathlib.Path:
        out = HERE / "results" / f"m0_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(self.steps, ensure_ascii=False, indent=1, default=str))
        return out


def track_rows(engine: ptsl.Engine) -> list[dict]:
    rows = []
    for t in engine.track_list():
        rows.append({"id": t.id, "name": t.name, "index": t.index,
                     "type": pt.TrackType.Name(t.type), "format": pt.TrackFormat.Name(t.format),
                     "color": t.color, "clips": t.track_attributes.contains_clips})
    return rows


def run_op(engine: ptsl.Engine, op: Operation) -> dict:
    engine.client.run(op)
    if op.response is None:
        return {}
    return json_format.MessageToDict(op.response, preserving_proto_field_name=True)


def session_info(engine: ptsl.Engine) -> dict:
    return {"name": engine.session_name(), "path": engine.session_path(),
            "sample_rate": engine.session_sample_rate()}


def colour_palette(engine: ptsl.Engine) -> dict:
    out = run_op(engine, CId_GetColorPalette(color_palette_target=pt.CPTarget_Tracks))
    colours = out.get("color_list", [])
    return {"count": len(colours), "first": colours[:8]}


def connect(log: Log) -> ptsl.Engine | None:
    engine = log.step("connect (RegisterConnection)", ptsl.Engine,
                      company_name=COMPANY, application_name=APP)
    if engine is not None:
        log.step("PTSL version", engine.ptsl_version)
    return engine


def cmd_info() -> int:
    log = Log()
    engine = connect(log)
    if engine is None:
        print("Cannot connect. Is Pro Tools running?")
        log.save()
        return 1
    if log.step("session info", session_info, engine) is not None:
        log.step("track list", track_rows, engine)
        log.step("colour palette (GetColorPalette)", colour_palette, engine)
    engine.close()
    print("log:", log.save())
    return 0


def ensure_test_session(log: Log, engine: ptsl.Engine) -> bool:
    try:
        name = engine.session_name()
    except Exception:
        name = None
    if name == TEST_SESSION:
        # Start every run from an empty test session; the folder holds only what this
        # script created.
        log.step("close test session without saving", engine.close_session, False)
        shutil.rmtree(SESSION_DIR / TEST_SESSION, ignore_errors=True)
        name = None
    if name:
        print(f"Session '{name}' is open. Close it (or open {TEST_SESSION}) and rerun; "
              "this script changes only the test session.")
        return False
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    existing = SESSION_DIR / TEST_SESSION / f"{TEST_SESSION}.ptx"
    if existing.exists():
        log.step("open test session", engine.open_session, str(existing))
    else:
        def create():
            b = engine.create_session(TEST_SESSION, str(SESSION_DIR))
            b.sample_rate(48000)
            b.bit_depth(24)
            b.wave_format()
            b.interleaved(True)
            b.create()
        log.step("create test session (48 kHz, 24-bit)", create)
    return log.step("session info", session_info, engine) is not None


def import_files(engine: ptsl.Engine, files: list[pathlib.Path], operation) -> dict:
    op_name = pt.AudioOperations.Name(operation)
    audio = pt.AudioData(
        file_list=[str(f) for f in files], audio_operations=operation,
        destination_path=str(pathlib.Path(engine.session_path()).parent / "Audio Files"),
        audio_destination=pt.MD_NewTrack, audio_location=pt.ML_SessionStart,
        location_data=pt.SpotLocationData(location_type=pt.SLType_Start,
                                          location_options=pt.TOOptions_TimeCode,
                                          location_value=""))
    out = run_op(engine, CId_Import(import_type=pt.IType_Audio, audio_data=audio))
    return {"files": [f.name for f in files], "operation": op_name, "response": out}


def new_tracks(before: list[dict], after: list[dict]) -> list[dict]:
    ids = {r["id"] for r in before}
    return [r for r in after if r["id"] not in ids]


def cmd_run_all(stems_dir: pathlib.Path) -> int:
    log = Log()
    engine = connect(log)
    if engine is None or not ensure_test_session(log, engine):
        print("log:", log.save())
        return 1
    stems = sorted(p for p in stems_dir.iterdir() if p.suffix.lower() == ".wav")
    same_rate = [p for p in stems if "44k" not in p.name]
    other_rate = [p for p in stems if "44k" in p.name]

    before = log.step("track list (before)", track_rows, engine) or []

    # 1. Import files that match the session rate as copies, then the 44.1 kHz file twice:
    #    once as a copy (expected to be refused or to play at the wrong speed) and once converted.
    log.step("import 48 kHz files (CopyAudio, new tracks, session start)",
             import_files, engine, same_rate, pt.CopyAudio)
    log.step("import 44.1 kHz file (CopyAudio)", import_files, engine, other_rate, pt.CopyAudio)
    log.step("import 44.1 kHz file (ConvertAudio)", import_files, engine, other_rate, pt.ConvertAudio)
    after = log.step("track list (after import)", track_rows, engine) or []
    created = new_tracks(before, after)
    log.step("tracks created by import", lambda: created)

    # 2. Rename: plain rename, a non-ASCII source name, and two tracks to the same name.
    plan = {"Kick In": "KICK IN", "SNR_Top": "SNARE TOP", "鋼琴": "Piano", "OH": "OH"}
    for row in created:
        new = plan.get(row["name"])
        if new and new != row["name"]:
            log.step(f"rename '{row['name']}' -> '{new}'",
                     engine.rename_target_track, row["name"], new)
    log.step("rename 'Bass DI' -> 'Piano' (name already taken)",
             engine.rename_target_track, "Bass DI", "Piano")
    log.step("rename 'No Such Track' -> 'X' (track does not exist)",
             engine.rename_target_track, "No Such Track", "X")
    log.step("track list (after rename)", lambda: [r["name"] for r in track_rows(engine)])

    # 3. Create tracks (used later for routing): one stereo aux and one mono audio track.
    log.step("create stereo aux 'DRUM BUS'", engine.create_new_tracks, 1, "DRUM BUS",
             pt.TF_Stereo, pt.TT_Aux, pt.TTB_Samples)
    log.step("create mono audio 'Spare'", engine.create_new_tracks, 1, "Spare",
             pt.TF_Mono, pt.TT_Audio, pt.TTB_Samples)

    # 4. Preview of M0-b: colour by palette index through PTSL.
    log.step("colour palette (GetColorPalette)", colour_palette, engine)
    log.step("SetTrackColor KICK IN, SNARE TOP -> index 5", run_op, engine,
             CId_SetTrackColor(track_names=["KICK IN", "SNARE TOP"], color_index=5))

    log.step("track list (final)", track_rows, engine)
    engine.close()
    print("log:", log.save())
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "info":
        return cmd_info()
    if len(sys.argv) == 3 and sys.argv[1] == "run-all":
        return cmd_run_all(pathlib.Path(sys.argv[2]).resolve())
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
