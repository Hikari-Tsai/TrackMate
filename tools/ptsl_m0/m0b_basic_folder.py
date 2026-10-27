"""Check the v1 grouping flow with Basic Folders: one folder per category, stems imported
into it by selecting the folder first, then folder and member tracks coloured.

Starts from a fresh test session. Usage: python m0b_basic_folder.py
"""
from __future__ import annotations

import shutil
import sys

from ptsl import PTSL_pb2 as pt

import m0_probe as m

STEMS = m.ROOT / "build" / "m0_stems"
GROUPS = {"DRUMS": ["Kick In.wav", "SNR_Top.wav", "OH.wav"], "KEYS": ["鋼琴.wav"],
          "BASS": ["Bass DI.wav"]}
COLOURS = {"DRUMS": 5, "KEYS": 20, "BASS": 40}


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
    if not m.ensure_test_session(log, engine):
        return 1
    for folder, files in GROUPS.items():
        log.step(f"create basic folder {folder}", engine.create_new_tracks, 1, folder,
                 pt.TF_Stereo, pt.TT_BasicFolder, pt.TTB_Samples)
        log.step(f"select {folder}", engine.select_tracks_by_name, [folder])
        log.step(f"import into {folder}", m.import_files, engine, [STEMS / f for f in files],
                 pt.ConvertAudio)
        members = [t.name for t in engine.track_list() if t.parent_folder_name == folder]
        log.step(f"colour {folder} and members", m.run_op, engine,
                 m.CId_SetTrackColor(track_names=[folder] + members, color_index=COLOURS[folder]))
    log.step("final layout", lambda: [(t.name, pt.TrackType.Name(t.type), t.parent_folder_name, t.color)
                                      for t in engine.track_list()])
    engine.close()
    print("log:", log.save())
    return 0


if __name__ == "__main__":
    sys.exit(main())
