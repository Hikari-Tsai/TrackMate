"""M0-b follow-up: route by path name, routing folders, and clip-list import plus spot.

Runs in the test session after m0b_routing.py (which creates the routing folder VOCALS).
Usage: python m0b_folder.py
"""
from __future__ import annotations

import sys

from ptsl import PTSL_pb2 as pt, ops
from ptsl.ops import Operation

import m0_probe as m
from m0b_routing import CId_SetTrackMainOutputAssignments

STEMS = m.ROOT / "build" / "m0_stems"


class CId_ImportAudioToClipList(Operation):
    pass


class CId_SpotClipsByID(Operation):
    pass


class CId_CreateNewTracks(Operation):
    pass


def folder_view(engine) -> list[tuple]:
    return [(t.name, pt.TrackType.Name(t.type), t.parent_folder_name) for t in engine.track_list()]


def main() -> int:
    log = m.Log()
    engine = m.connect(log)
    if engine is None or engine.session_name() != m.TEST_SESSION:
        print("Run m0_probe.py run-all and m0b_routing.py first.")
        return 1
    log.step("assign OH -> 'Analogue 1-2' given as a name", m.run_op, engine,
             CId_SetTrackMainOutputAssignments(track_names=["OH"], signalpath_ids=["Analogue 1-2"]))

    # New track created right after the routing folder: does it land inside it?
    log.step("create audio 'Vox A' after VOCALS", m.run_op, engine, CId_CreateNewTracks(
        number_of_tracks=1, track_name="Vox A", track_format=pt.TF_Mono, track_type=pt.TT_Audio,
        track_timebase=pt.TTB_Samples, insertion_point_position=pt.TIPoint_After,
        insertion_point_track_name="VOCALS"))
    log.step("tracks and parent folders", folder_view, engine)

    # Import with the folder selected: where do the new tracks go?
    log.step("select VOCALS", engine.select_tracks_by_name, ["VOCALS"])
    log.step("import 'Lead Vox 44k.wav' with VOCALS selected", m.import_files, engine,
             [STEMS / "Lead Vox 44k.wav"], pt.ConvertAudio)
    log.step("tracks and parent folders after import", folder_view, engine)

    # Clip-list import, then spot onto an existing track (would let a template's tracks
    # keep their routing).
    clips = log.step("import Bass DI.wav to clip list", m.run_op, engine, CId_ImportAudioToClipList(
        file_list=[str(STEMS / "Bass DI.wav")], audio_operations=pt.ConvertAudio,
        destination_path=str(m.pathlib.Path(engine.session_path()).parent / "Audio Files"))) or {}
    ids = [c for e in clips.get("file_list", []) for f in e.get("destination_file_list", []) for c in f.get("clip_id_list", [])]
    log.step("clip ids from import", lambda: ids or clips)
    if ids:
        log.step("spot clip onto 'Vox A' at session start", m.run_op, engine, CId_SpotClipsByID(
            src_clips=ids, dst_track_name="Vox A",
            dst_location_data=pt.SpotLocationData(location_type=pt.SLType_Start,
                                                  location_options=pt.TOOptions_Samples,
                                                  location_value="0")))
        log.step("Vox A contains clips",
                 lambda: [r["clips"] for r in m.track_rows(engine) if r["name"] == "Vox A"])
    engine.close()
    print("log:", log.save())
    return 0


if __name__ == "__main__":
    sys.exit(main())
