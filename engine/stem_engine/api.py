"""HTTP API for the desktop front end (README: Engine API).

Security: the server binds to 127.0.0.1 only,
every endpoint except /health needs `Authorization: Bearer <token>` with a token generated
at each start, and requests whose Host header is not local are refused (DNS rebinding).
"""
from __future__ import annotations

import hmac
import pathlib
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .engine import Engine
from .models import DownloadInProgress
from . import apply as apply_mod
from . import tempo as tempo_mod
from .protools import NoSession, ProToolsLost, ProToolsNotResponding, ProToolsUnavailable, session_snapshot

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def fail(status: int, code: str, message: str, **extra) -> HTTPException:
    """Errors carry a stable `code` the app maps to its alerts, plus a readable message."""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def pro_tools_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProToolsLost):
        return fail(503, "pro_tools_lost", str(exc))
    if isinstance(exc, ProToolsNotResponding):
        return fail(504, "pro_tools_not_responding", str(exc))
    if isinstance(exc, ProToolsUnavailable):
        return fail(503, "pro_tools_not_running", "Pro Tools is not running.")
    if isinstance(exc, NoSession):
        return fail(409, "no_session", "No session is open in Pro Tools.")
    raise exc


class AnalyzeRequest(BaseModel):
    files: list[str] = Field(..., min_length=1, max_length=512)
    audio: Literal["none", "auto", "all"] = "auto"
    stereo: bool = True


class FeedbackRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    instrument: str


class DownloadRequest(BaseModel):
    models: list[str] | None = None


class ApplyTrack(BaseModel):
    file: str
    name: str = Field(..., min_length=1, max_length=256)
    category: str
    color_index: int | None = Field(default=None, ge=1, le=69)
    folder: str | None = Field(default=None, max_length=64)
    mono: bool = False


class ApplyRequest(BaseModel):
    tracks: list[ApplyTrack] = Field(..., min_length=1, max_length=512)
    dry_run: bool = False


class TempoTrack(BaseModel):
    file: str
    category: str = "other"


class TempoRequest(BaseModel):
    tracks: list[TempoTrack] = Field(..., min_length=1, max_length=512)


class TempoApplyRequest(BaseModel):
    beats: list[float] = Field(..., min_length=2, max_length=20000)
    downbeats: list[float] = Field(default_factory=list, max_length=20000)
    duration: float = Field(..., gt=0)
    mode: Literal["constant", "variable"]
    bpm: float | None = Field(default=None, ge=20, le=400)   # constant: the BPM to set
    factor: Literal[0.5, 1, 2] = 1                           # half / double time
    signature_beats: int | None = Field(default=None, ge=1, le=16)
    folder: str | None = None                                # where the .mid goes (else the cache)
    import_to_pro_tools: bool = True


def create_app(engine: Engine, token: str) -> FastAPI:
    app = FastAPI(title="TrackMate engine", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        return await call_next(request)

    def auth(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {token}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="missing or wrong token")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/models", dependencies=[Depends(auth)])
    def models() -> dict:
        return {"models": engine.models.summary(), "layers": engine.layers(), "dir": str(engine.models.dir)}

    @app.delete("/models", dependencies=[Depends(auth)])
    def clear_models() -> dict:
        """Deletes every downloaded model file. 409 while a download runs."""
        try:
            freed = engine.clear_models()
        except DownloadInProgress as exc:
            raise fail(409, "models_downloading", f"Cannot delete the models now: {exc}.")
        return {"freed_bytes": freed, "models": engine.models.summary(), "layers": engine.layers()}

    @app.post("/models/download", dependencies=[Depends(auth)])
    def download(req: DownloadRequest) -> dict:
        unknown = set(req.models or []) - set(engine.models.specs)
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown models: {sorted(unknown)}")
        engine.models.start(req.models)
        return {"models": engine.models.summary()}

    @app.post("/analyze", dependencies=[Depends(auth)])
    def analyze(req: AnalyzeRequest) -> dict:
        missing = [f for f in req.files if not pathlib.Path(f).is_file()]
        if missing:
            raise fail(404, "missing_files", "Some files cannot be found.", missing_files=missing)
        analyzer = engine.analyzer()
        return {"layers": engine.layers(), "tracks": analyzer.analyze(req.files, audio=req.audio,
                                                                     with_stereo=req.stereo)}

    @app.post("/feedback", dependencies=[Depends(auth)])
    def feedback(req: FeedbackRequest) -> dict:
        if req.instrument not in engine.kb.instruments:
            raise HTTPException(status_code=404, detail=f"unknown instrument {req.instrument!r}")
        try:
            key = engine.add_feedback(req.name, req.instrument)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"alias": key, "instrument": req.instrument}

    @app.get("/instruments", dependencies=[Depends(auth)])
    def instruments() -> dict:
        kb = engine.kb
        return {"categories": [{"id": cid, "name": c.get("name"), "zh": c.get("zh"), "ja": c.get("ja")}
                               for cid, c in kb.categories.items()],
                "instruments": [{"id": i.id, "label": i.canonical, "category": i.category}
                                for i in kb.instruments.values()]}

    @app.get("/categories", dependencies=[Depends(auth)])
    def categories() -> dict:
        a = engine.analyzer()
        return {"categories": a.categories, "palette": a.palette, "palette_index_base": 1}

    @app.get("/session", dependencies=[Depends(auth)])
    def session() -> dict:
        try:
            return session_snapshot(engine.config.ptsl_address)
        except ProToolsUnavailable as exc:
            raise pro_tools_error(exc) from exc

    @app.post("/apply", dependencies=[Depends(auth)])
    def apply(req: ApplyRequest) -> dict:
        missing = [t.file for t in req.tracks if not pathlib.Path(t.file).is_file()]
        if missing:
            raise fail(404, "missing_files", "Some files were moved or deleted.", missing_files=missing)
        a = engine.analyzer()
        unknown = sorted({t.category for t in req.tracks} - set(a.categories))
        if unknown:
            raise fail(422, "unknown_category", f"Unknown categories: {unknown}")
        try:
            return apply_mod.apply([t.model_dump() for t in req.tracks], a.categories, a.palette,
                                   engine.config.cache_dir / "apply", dry_run=req.dry_run,
                                   address=engine.config.ptsl_address)
        except (ProToolsUnavailable, NoSession) as exc:
            raise pro_tools_error(exc) from exc

    @app.post("/tempo", dependencies=[Depends(auth)])
    def tempo(req: TempoRequest) -> dict:
        missing = [t.file for t in req.tracks if not pathlib.Path(t.file).is_file()]
        if missing:
            raise fail(404, "missing_files", "Some files cannot be found.", missing_files=missing)
        tracker = engine.beat_tracker()
        if tracker is None:
            raise fail(503, "tempo_model_not_ready", "The tempo model is still downloading.")
        try:
            return tempo_mod.detect(tracker, [t.model_dump() for t in req.tracks]).to_dict()
        except tempo_mod.NoBeats as exc:
            raise fail(422, "no_beats", f"No steady beat found: {exc}.") from exc

    @app.post("/tempo/apply", dependencies=[Depends(auth)])
    def tempo_apply(req: TempoApplyRequest) -> dict:
        if req.mode == "constant" and req.bpm is None:
            raise fail(422, "bpm_required", "A constant tempo needs a BPM.")
        try:
            events, per_bar, average, check = tempo_mod.make_tempo(
                req.beats, req.downbeats, req.duration, req.mode, req.bpm, req.factor, req.signature_beats)
        except (tempo_mod.NoBeats, ValueError) as exc:
            raise fail(422, "no_beats", str(exc)) from exc
        folders = ([pathlib.Path(req.folder)] if req.folder else []) + [engine.config.cache_dir / "tempo"]
        midi = tempo_mod.write_midi(tempo_mod.tempo_midi(events, req.duration, per_bar),
                                    tempo_mod.midi_name(req.mode, average), folders)
        out = {"midi_path": str(midi), "mode": req.mode, "bpm": round(average, 2), "beats_per_bar": per_bar,
               "tempo_events": len(events), "imported": False, "applied": False}
        if req.import_to_pro_tools:
            try:
                out.update(tempo_mod.import_to_pro_tools(midi, events, per_bar, check, engine.config.ptsl_address),
                           imported=True)
            except (ProToolsUnavailable, NoSession) as exc:
                raise pro_tools_error(exc) from exc
        return out

    return app
