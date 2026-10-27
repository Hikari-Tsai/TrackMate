"""Pro Tools over PTSL, with the workarounds found in milestone M0 (tools/ptsl_m0,
docs/reports/pro-tools-integration.md):

- py-ptsl 602 `Engine.import_audio` sends import_type=1 (= IType_Session); audio needs IType_Audio
- always ConvertAudio: CopyAudio copies a 44.1 kHz file into a 48 kHz session unconverted
- rename needs the current name; a failed rename still reports success, so callers verify
- SetTrackColor / DeleteTracks reject requests carrying both track_ids and track_names, and
  py-ptsl serialises empty lists, so empty fields are dropped before sending
- a new track is inserted after the selected track (after the folder track = first member)
- PTSL has no tempo command, but importing a .mid through Import (IType_Audio) opens Pro Tools'
  MIDI Import Options dialog ("Import tempo map from MIDI File", Session Start); the call
  returns when the user presses OK, and also on Cancel, so the tempo is verified afterwards by
  reading a timeline position in Bars|Beats (GetTimelineSelection with time_scale)
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

COMPANY, APPLICATION = "ITRI", "TrackMate"


class ProToolsUnavailable(RuntimeError):
    """Pro Tools is not running (nothing answers on the PTSL port)."""


class ProToolsNotResponding(ProToolsUnavailable):
    """PTSL accepted the connection but did not answer in time (busy, or a dialog is open)."""


class ProToolsLost(ProToolsUnavailable):
    """The connection broke during an operation; part of it may already be done."""


class NoSession(RuntimeError):
    pass


def is_connection_error(exc: BaseException) -> bool:
    """gRPC errors that mean Pro Tools went away (quit, crashed, port closed)."""
    import grpc
    return isinstance(exc, grpc.RpcError) and exc.code() in (grpc.StatusCode.UNAVAILABLE,
                                                              grpc.StatusCode.DEADLINE_EXCEEDED)


def call_with_timeout(fn, seconds: float, what: str):
    """Run a PTSL call in a daemon thread; ProToolsNotResponding if it takes longer."""
    import threading
    box: dict = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # handed to the caller below
            box["error"] = exc

    t = threading.Thread(target=run, daemon=True, name=f"ptsl-{what}")
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise ProToolsNotResponding(f"Pro Tools did not answer within {seconds:.0f} s ({what})")
    if "error" in box:
        raise box["error"]
    return box["value"]


@dataclass
class TrackInfo:
    id: str
    name: str
    index: int
    type: str
    format: str
    color: str          # "#RRGGBB"
    folder: str | None
    has_clips: bool

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _ops():
    """Operation classes for commands py-ptsl does not wrap (or wraps wrongly)."""
    from ptsl.ops import Operation

    class DropEmpty(Operation):
        def json_messup(self, in_json: str) -> str:
            body = json.loads(in_json)
            return json.dumps({k: v for k, v in body.items() if v not in ([], "")})

    class CId_Import(Operation):
        pass

    class CId_SetTrackColor(DropEmpty):
        pass

    class CId_RenameTargetTrack(DropEmpty):
        pass

    class CId_CreateNewTracks(DropEmpty):
        pass

    class CId_GetColorPalette(Operation):
        pass

    class CId_GetTimelineSelection(Operation):
        pass

    class CId_SetTimelineSelection(Operation):
        pass

    return {c.__name__: c for c in (CId_Import, CId_SetTrackColor, CId_RenameTargetTrack,
                                    CId_CreateNewTracks, CId_GetColorPalette, CId_GetTimelineSelection,
                                    CId_SetTimelineSelection)}


class ProTools:
    def __init__(self, address: str = "localhost:31416"):
        import ptsl
        from ptsl import PTSL_pb2
        self.pt = PTSL_pb2
        self.ops = _ops()
        try:
            self.engine = ptsl.Engine(company_name=COMPANY, application_name=APPLICATION, address=address)
            self.version = self.engine.ptsl_version()
        except Exception as exc:
            raise ProToolsUnavailable(f"cannot reach Pro Tools on {address}: {exc}") from exc

    def close(self) -> None:
        self.engine.close()

    def __enter__(self) -> ProTools:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _run(self, op) -> dict:
        from google.protobuf import json_format
        self.engine.client.run(op)
        if op.response is None:
            return {}
        return json_format.MessageToDict(op.response, preserving_proto_field_name=True)

    # -------------------------------------------------------------- reading
    def session(self) -> dict:
        try:
            name = self.engine.session_name()
        except Exception as exc:
            raise NoSession("no session is open in Pro Tools") from exc
        return {"name": name, "path": self.engine.session_path(), "sample_rate": self.engine.session_sample_rate()}

    def tracks(self) -> list[TrackInfo]:
        pt = self.pt
        return [TrackInfo(t.id, t.name, t.index, pt.TrackType.Name(t.type), pt.TrackFormat.Name(t.format),
                          "#" + t.color[3:].upper() if len(t.color) == 9 else t.color.upper(),
                          t.parent_folder_name or None, t.track_attributes.contains_clips)
                for t in self.engine.track_list()]

    def palette(self) -> list[str]:
        out = self._run(self.ops["CId_GetColorPalette"](color_palette_target=self.pt.CPTarget_Tracks))
        return ["#" + c[3:].upper() for c in out.get("color_list", [])]

    def bars_beats_at(self, sample: int) -> str:
        """The Bars|Beats position ("   25| 2| 000") of a sample position from the session start.
        Moves the timeline selection there to read it, then puts the selection back."""
        pt, get, put = self.pt, self.ops["CId_GetTimelineSelection"], self.ops["CId_SetTimelineSelection"]
        before = self._run(get(time_scale=pt.TOOptions_Samples))
        try:
            self._run(put(in_time=str(sample), out_time=str(sample)))
            return self._run(get(time_scale=pt.TOOptions_BarsBeats))["in_time"]
        finally:
            self._run(put(in_time=before["in_time"], out_time=before["out_time"]))

    # -------------------------------------------------------------- writing
    def create_folder(self, name: str) -> str:
        """Basic Folder at the end of the session; returns the name Pro Tools gave it."""
        pt = self.pt
        out = self._run(self.ops["CId_CreateNewTracks"](
            number_of_tracks=1, track_name=name, track_format=pt.TF_Stereo, track_type=pt.TT_BasicFolder,
            track_timebase=pt.TTB_Samples, insertion_point_position=pt.TIPoint_Last))
        return (out.get("created_track_names") or [name])[0]

    def select(self, names: list[str]) -> None:
        self.engine.select_tracks_by_name(names)

    def import_audio(self, path: str, session_path: str) -> None:
        pt = self.pt
        audio = pt.AudioData(
            file_list=[path], audio_operations=pt.ConvertAudio,
            destination_path=str(pathlib.Path(session_path).parent / "Audio Files"),
            audio_destination=pt.MD_NewTrack, audio_location=pt.ML_SessionStart,
            location_data=pt.SpotLocationData(location_type=pt.SLType_Start,
                                              location_options=pt.TOOptions_TimeCode, location_value=""))
        self._run(self.ops["CId_Import"](import_type=pt.IType_Audio, audio_data=audio))

    def import_midi(self, path: str, session_path: str) -> None:
        """Opens Pro Tools' MIDI Import Options dialog and returns once the user closes it."""
        self.import_audio(path, session_path)

    def rename(self, track_id: str, current: str, new: str) -> None:
        self._run(self.ops["CId_RenameTargetTrack"](track_id=track_id, current_name=current, new_name=new))

    def set_color(self, names: list[str], color_index: int) -> int:
        out = self._run(self.ops["CId_SetTrackColor"](track_names=names, color_index=color_index))
        return int(out.get("success_count", 0))


def session_snapshot(address: str = "localhost:31416", timeout: float = 10.0) -> dict:
    return call_with_timeout(lambda: _session_snapshot(address), timeout, "read session")


def _session_snapshot(address: str) -> dict:
    with ProTools(address) as p:
        try:
            session = p.session()
        except NoSession:
            return {"connected": True, "ptsl_version": p.version, "session": None, "tracks": []}
        return {"connected": True, "ptsl_version": p.version, "session": session,
                "tracks": [t.to_dict() for t in p.tracks()]}
