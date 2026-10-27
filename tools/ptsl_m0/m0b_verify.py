"""M0-b: check, by listening to bounces, that tracks imported into a routing folder are routed
through it.

PTSL cannot read a track's output assignment, so the check uses audio. In a fresh test
session:
  1. create routing folder DRUMS, select it, import Kick/Snare/OH  -> tracks inside DRUMS
  2. import Bass DI with nothing selected                          -> track outside
  3. mute Bass DI; bounce the main output with DRUMS muted, DRUMS inactive, and DRUMS on
If the drum tracks are routed through the folder, the first two bounces are silent while the
drum tracks themselves stay unmuted and active, and the third is not silent.

Usage: python m0b_verify.py
"""
from __future__ import annotations

import shutil
import sys

import numpy as np
import soundfile as sf
from ptsl import PTSL_pb2 as pt, ops
from ptsl.ops import Operation

import m0_probe as m
from m0b_routing import CId_GetExportMixSourceList

STEMS = m.ROOT / "build" / "m0_stems"
BOUNCE_DIR = m.ROOT / "build" / "m0_bounce"


class CId_ExportMix(Operation):
    pass


def bounce(engine, name: str, output: str, seconds: int = 8) -> dict:
    target = BOUNCE_DIR / f"{name}.wav"
    target.unlink(missing_ok=True)
    m.run_op(engine, CId_ExportMix(
        file_name=name, file_type=pt.EMFType_WAV,
        mix_source_list=[pt.EM_SourceInfo(source_type=pt.EMSType_Output, name=output)],
        audio_info=pt.EM_AudioInfo(compression_type=pt.CT_PCM, export_format=pt.EF_Interleaved,
                                   bit_depth=pt.Bit24, sample_rate=pt.SR_48000,
                                   delivery_format=pt.EM_DF_SingleFile),
        # Without the trailing slash Pro Tools fails with an assertion in Sys_FileLocMacOS.cpp.
        location_info=pt.EM_LocationInfo(file_destination=pt.EM_FD_Directory,
                                         directory=str(BOUNCE_DIR) + "/"),
        offline_bounce=pt.TB_True,
        start_time=pt.TimelineLocation(location="0", time_type=pt.TLType_Samples),
        end_time=pt.TimelineLocation(location=str(seconds * 48000), time_type=pt.TLType_Samples)))
    files = sorted(BOUNCE_DIR.glob(f"{name}*.wav"))
    if not files:
        return {"file": None}
    x, _ = sf.read(files[0], dtype="float64", always_2d=True)
    peak = float(np.abs(x).max())
    return {"file": files[0].name, "peak_dbfs": round(20 * np.log10(peak), 1) if peak else None}


def states(engine, names: list[str]) -> dict:
    out = {}
    for t in engine.track_list():
        if t.name in names:
            a = t.track_attributes
            out[t.name] = {"folder": t.parent_folder_name, "muted": a.is_muted, "inactive": a.is_inactive}
    return out


def main() -> int:
    log = m.Log()
    engine = m.connect(log)
    if engine is None:
        return 1
    try:
        name = engine.session_name()
    except Exception:
        name = None
    if name not in (None, m.TEST_SESSION):
        print(f"Session '{name}' is open; close it first.")
        return 1
    if name == m.TEST_SESSION:
        log.step("close test session without saving", engine.close_session, False)
    shutil.rmtree(m.SESSION_DIR / m.TEST_SESSION, ignore_errors=True)
    shutil.rmtree(BOUNCE_DIR, ignore_errors=True)
    BOUNCE_DIR.mkdir(parents=True)
    if not m.ensure_test_session(log, engine):
        return 1

    log.step("create routing folder 'DRUMS'", engine.create_new_tracks, 1, "DRUMS",
             pt.TF_Stereo, pt.TT_RoutingFolder, pt.TTB_Samples)
    log.step("select DRUMS", engine.select_tracks_by_name, ["DRUMS"])
    drums = [STEMS / "SNR_Top.wav", STEMS / "Kick In.wav", STEMS / "OH.wav"]
    log.step("import Snare, Kick, OH with DRUMS selected", m.import_files, engine, drums, pt.ConvertAudio)
    log.step("select nothing", engine.select_tracks_by_name, [])
    log.step("import Bass DI with nothing selected", m.import_files, engine,
             [STEMS / "Bass DI.wav"], pt.ConvertAudio)
    names = ["DRUMS", "Kick In", "SNR_Top", "OH", "Bass DI"]
    log.step("track order", lambda: [(t.name, t.parent_folder_name) for t in engine.track_list()])

    # The output list only contains outputs that tracks use, so read it after importing.
    outputs = log.step("main output names", lambda: m.run_op(
        engine, CId_GetExportMixSourceList(type=pt.EMSType_Output)).get("source_list", [])) or []
    main_out = outputs[0] if outputs else "Out 1-2"
    log.step("mute Bass DI", engine.set_track_mute_state, ["Bass DI"], True)
    log.step("bounce: everything on (Bass DI muted)", bounce, engine, "a_drums_on", main_out)
    log.step("mute DRUMS folder", engine.set_track_mute_state, ["DRUMS"], True)
    log.step("states with DRUMS muted", states, engine, names)
    log.step("bounce: DRUMS muted", bounce, engine, "b_drums_muted", main_out)
    log.step("unmute DRUMS folder", engine.set_track_mute_state, ["DRUMS"], False)
    log.step("make DRUMS inactive", engine.set_track_inactive_state, ["DRUMS"], True)
    log.step("states with DRUMS inactive", states, engine, names)
    log.step("bounce: DRUMS inactive", bounce, engine, "c_drums_inactive", main_out)
    log.step("make DRUMS active", engine.set_track_inactive_state, ["DRUMS"], False)
    engine.close()
    print("log:", log.save())
    return 0


if __name__ == "__main__":
    sys.exit(main())
