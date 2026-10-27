"""M0-b technical check: create buses, assign track outputs, and delete tracks through PTSL.

Runs in the test session (M0_PTSL_Test) right after `m0_probe.py run-all`, which leaves
these tracks: Bass DI, Gtr L only, KICK IN, OH, SNARE TOP, Piano, Lead Vox 44k,
Lead Vox 44k.1, DRUM BUS (stereo aux), Spare (empty mono audio).

PTSL has no command that reads a track's output assignment back, so the script records
what each command returns, and the bus list from GetExportMixSourceList before and after.
Usage: python m0b_routing.py
"""
from __future__ import annotations

import sys

import ptsl
from ptsl import PTSL_pb2 as pt
from ptsl.ops import Operation

import m0_probe as m


class CId_CreateSignalPath(Operation):
    pass


class CId_SetTrackMainOutputAssignments(m.DropEmptyLists):
    pass


class CId_GetExportMixSourceList(Operation):
    pass


def sources(engine: ptsl.Engine, kind) -> list[str]:
    return m.run_op(engine, CId_GetExportMixSourceList(type=kind)).get("source_list", [])


def create_path(engine: ptsl.Engine, name: str, kind, fmt) -> dict:
    out = m.run_op(engine, CId_CreateSignalPath(signalpath_name=name, signalpath_type=kind,
                                                signalpath_format=fmt))
    return out.get("signalpath_info", out)


def assign(engine: ptsl.Engine, path_id: str, names=None, ids=None) -> dict:
    return m.run_op(engine, CId_SetTrackMainOutputAssignments(
        track_names=names or [], track_ids=ids or [], signalpath_ids=[path_id]))


def delete(engine: ptsl.Engine, names=None, ids=None) -> dict:
    return m.run_op(engine, m.CId_DeleteTracks(track_names=names or [], track_ids=ids or []))


def main() -> int:
    log = m.Log()
    engine = m.connect(log)
    if engine is None or engine.session_name() != m.TEST_SESSION:
        print("Run m0_probe.py run-all first so the test session is open.")
        return 1
    rows = {r["name"]: r for r in m.track_rows(engine)}
    log.step("tracks at start", lambda: list(rows))
    log.step("bus list before (GetExportMixSourceList Bus)", sources, engine, pt.EMSType_Bus)
    log.step("output list before (GetExportMixSourceList Output)", sources, engine, pt.EMSType_Output)

    # 1. Buses
    drums = log.step("create stereo bus 'DRUMS'", create_path, engine, "DRUMS",
                     pt.SPType_Bus, pt.SFormat_Stereo) or {}
    bass = log.step("create mono bus 'BASS'", create_path, engine, "BASS",
                    pt.SPType_Bus, pt.SFormat_Mono) or {}
    log.step("create stereo bus 'DRUMS' again (name taken)", create_path, engine, "DRUMS",
             pt.SPType_Bus, pt.SFormat_Stereo)
    log.step("create stereo output path 'STEMS OUT'", create_path, engine, "STEMS OUT",
             pt.SPType_Output, pt.SFormat_Stereo)
    log.step("bus list after creating buses", sources, engine, pt.EMSType_Bus)

    # 2. Output assignments
    if drums.get("id"):
        log.step("assign KICK IN, SNARE TOP, OH -> DRUMS (by name)", assign, engine, drums["id"],
                 names=["KICK IN", "SNARE TOP", "OH"])
    if bass.get("id"):
        log.step("assign Bass DI -> BASS (by track id)", assign, engine, bass["id"],
                 ids=[rows["Bass DI"]["id"]])
        log.step("assign Piano (stereo track) -> BASS (mono bus)", assign, engine, bass["id"],
                 names=["Piano"])
    log.step("assign Gtr L only -> bogus path id", assign, engine,
             "{00000000-00000000-00000000-00000000}", names=["Gtr L only"])
    log.step("assign No Such Track -> DRUMS", assign, engine, drums.get("id", ""),
             names=["No Such Track"])
    log.step("create stereo bus 'DRUMS' again after assigning (in_use?)", create_path, engine,
             "DRUMS", pt.SPType_Bus, pt.SFormat_Stereo)

    # 3. Routing folder: does creating one also create a bus we can route to?
    log.step("create routing folder 'VOCALS'", engine.create_new_tracks, 1, "VOCALS",
             pt.TF_Stereo, pt.TT_RoutingFolder, pt.TTB_Samples)
    log.step("bus list after routing folder", sources, engine, pt.EMSType_Bus)

    # 4. Delete tracks
    log.step("delete 'Spare' (empty, by name)", delete, engine, names=["Spare"])
    log.step("delete 'Lead Vox 44k' (has clips, by id)", delete, engine,
             ids=[rows["Lead Vox 44k"]["id"]])
    log.step("delete 'No Such Track'", delete, engine, names=["No Such Track"])
    log.step("tracks at end", lambda: [(r["name"], r["type"], r["format"]) for r in m.track_rows(engine)])
    engine.close()
    print("log:", log.save())
    return 0


if __name__ == "__main__":
    sys.exit(main())
