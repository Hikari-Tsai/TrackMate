"""POST /apply (milestone M3): put the confirmed tracks into the open Pro Tools session.

For each category, in the order of categories.json: create a Basic Folder (or join one the
request names, or one of the same name already in the session), then import the files one by
one, each after the previously placed track, so the folder keeps the order the front end sent. Every new track is found by its track ID and renamed right away to
its final name; final names are made unique against the session beforehand, so a rename never
hits a taken name. Colours are set per colour group, and at the end the track list is read
again to verify name, folder and colour of every track (PTSL reports failed renames as
success).
"""
from __future__ import annotations

import pathlib
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field

from . import stereo
from .protools import ProTools, ProToolsLost, ProToolsUnavailable, call_with_timeout, is_connection_error

# Characters that are unsafe in Pro Tools track and file names are replaced.
_BAD_CHARS = re.compile(r'[/:"?*<>|\\]')
MAX_NAME = 31


@dataclass
class PlannedTrack:
    file: str
    final_name: str
    category: str
    folder: str
    color_index: int
    mono: bool                      # convert to mono before import
    stereo_action: str | None = None
    source: str | None = None       # file actually imported (converted copy when mono)
    result: dict = field(default_factory=dict)


@dataclass
class PlannedFolder:
    name: str
    category: str
    color_index: int
    exists: bool
    tracks: list[PlannedTrack] = field(default_factory=list)


def clean_name(name: str) -> str:
    s = _BAD_CHARS.sub("_", " ".join(name.split()))
    return s[:MAX_NAME].rstrip() or "Track"


def unique(name: str, taken: set[str]) -> str:
    """'Kick In' -> 'Kick In 2' -> 'Kick In 3' ... until free. Case-sensitive, as in Pro Tools
    ('KICK IN' and 'Kick In' can coexist; checked on Pro Tools 26.4)."""
    if name not in taken:
        return name
    k = 2
    while True:
        cand = clean_name(f"{name[:MAX_NAME - len(str(k)) - 1].rstrip()} {k}")
        if cand not in taken:
            return cand
        k += 1


def build_plan(requests: list[dict], categories: dict, existing: list[dict]) -> list[PlannedFolder]:
    """requests: [{file, name, category, color_index?, folder?, new_folder?, mono?}] in display
    order. existing: current session tracks [{name, type, folder}]. Pure function (no Pro Tools).

    Where a track goes: `folder` names a Basic Folder instead of the category's one; a folder
    already in the session is joined, any other name is created. `new_folder` always creates one,
    with a free name ('DRUMS 2') even when a folder of that name exists."""
    taken = {t["name"] for t in existing}
    existing_folders = {t["name"] for t in existing if t["type"] == "BasicFolder"}
    order = list(categories)
    # One planned folder per (wanted name, new or not): every track that asks for the same thing
    # lands in the same folder, whatever name it ended up with.
    folders: dict[tuple[str, bool], PlannedFolder] = {}
    for req in sorted(requests, key=lambda r: order.index(r["category"]) if r["category"] in order else len(order)):
        cat = req["category"] if req["category"] in categories else "other"
        spec = categories[cat]
        wanted = clean_name(req.get("folder") or spec["folder"])
        key = (wanted, bool(req.get("new_folder")))
        folder = folders.get(key)
        if folder is None:
            exists = wanted in existing_folders and not key[1]
            # A new folder gets a free name: not an existing folder's, nor any other track's.
            fname = wanted if exists else unique(wanted, taken)
            if not exists:
                taken.add(fname)
            folder = folders[key] = PlannedFolder(fname, cat, spec["color_index"], exists)
        final = unique(clean_name(req["name"]), taken)
        taken.add(final)
        folder.tracks.append(PlannedTrack(
            file=req["file"], final_name=final, category=cat, folder=folder.name,
            color_index=int(req.get("color_index") or spec["color_index"]),
            mono=bool(req.get("mono"))))
    return list(folders.values())


def plan_to_dict(plan: list[PlannedFolder]) -> list[dict]:
    return [{"folder": f.name, "category": f.category, "color_index": f.color_index, "exists": f.exists,
             "tracks": [{"file": t.file, "final_name": t.final_name, "color_index": t.color_index,
                         "mono": t.mono, "stereo_action": t.stereo_action} for t in f.tracks]}
            for f in plan]


def apply(requests: list[dict], categories: dict, palette: list[str], staging_root: pathlib.Path,
          dry_run: bool = False, address: str = "localhost:31416") -> dict:
    """Raises ProToolsUnavailable (not running), ProToolsNotResponding, NoSession, or
    ProToolsLost when Pro Tools goes away after something was already changed."""
    log: list[str] = []
    try:
        return _apply(requests, categories, palette, staging_root, dry_run, address, log)
    except Exception as exc:
        if not is_connection_error(exc):
            raise
        if not log:
            raise ProToolsUnavailable(f"Pro Tools stopped answering: {exc.code().name}") from exc
        raise ProToolsLost(f"Pro Tools stopped answering after {len(log)} step(s); the session may already "
                           f"contain some of the new folders or tracks. Last step: {log[-1]}") from exc


def _apply(requests: list[dict], categories: dict, palette: list[str], staging_root: pathlib.Path,
           dry_run: bool, address: str, log: list[str]) -> dict:
    t0 = time.perf_counter()
    with ProTools(address) as pro:
        session = call_with_timeout(pro.session, 10, "read session")
        before = pro.tracks()
        plan = build_plan(requests, categories,
                          [{"name": t.name, "type": t.type, "folder": t.folder} for t in before])
        if dry_run:
            return {"session": session, "dry_run": True, "plan": plan_to_dict(plan), "ok": True}

        staging = staging_root / uuid.uuid4().hex[:12]
        try:
            for folder in plan:
                tracks_now = pro.tracks()
                if folder.exists:
                    members = [t.name for t in tracks_now if t.folder == folder.name]
                    anchor = members[-1] if members else folder.name
                else:
                    created = pro.create_folder(folder.name)
                    if created != folder.name:
                        log.append(f"folder {folder.name!r} was created as {created!r}")
                        for t in folder.tracks:
                            t.folder = created
                        folder.name = created
                    anchor = folder.name
                    log.append(f"created folder {folder.name}")
                for i, t in enumerate(folder.tracks):
                    res = t.result
                    res.update(file=t.file, final_name=t.final_name, folder=folder.name, errors=[])
                    try:
                        t.source = _stage(t, staging / f"{folder.name}_{i}")
                        ids_before = {x.id for x in pro.tracks()}
                        pro.select([anchor])
                        pro.import_audio(t.source, session["path"])
                        new = [x for x in pro.tracks() if x.id not in ids_before]
                        if len(new) != 1:
                            raise RuntimeError(f"expected 1 new track after import, found {len(new)}")
                        track = new[0]
                        res["track_id"] = track.id
                        if track.name != t.final_name:
                            pro.rename(track.id, track.name, t.final_name)
                        # Next file goes after this track; use the name Pro Tools really has.
                        anchor = next(x.name for x in pro.tracks() if x.id == track.id)
                        res["pt_name"] = anchor
                        log.append(f"imported {pathlib.Path(t.source).name} -> {t.final_name}")
                    except Exception as exc:
                        if is_connection_error(exc):
                            raise  # Pro Tools is gone: stop instead of failing every remaining track
                        res["errors"].append(f"import: {type(exc).__name__}: {exc}")
            # Colour: new folder tracks and all members grouped by palette index. A folder that
            # was already in the session keeps the colour it has.
            groups: dict[int, list[str]] = {}
            for folder in plan:
                if not folder.exists:
                    groups.setdefault(folder.color_index, []).append(folder.name)
                for t in folder.tracks:
                    if "pt_name" in t.result:
                        groups.setdefault(t.color_index, []).append(t.result["pt_name"])
            for idx, names in groups.items():
                n = pro.set_color(names, idx)
                log.append(f"colour {idx}: {n}/{len(names)} tracks")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        after = {t.id: t for t in pro.tracks()}
        ok = True
        for folder in plan:
            for t in folder.tracks:
                res = t.result
                track = after.get(res.get("track_id", ""))
                res["name_ok"] = bool(track and track.name == t.final_name)
                res["folder_ok"] = bool(track and track.folder == folder.name)
                res["color_ok"] = bool(track and track.color == palette[t.color_index - 1])
                res["pt_name"] = track.name if track else None
                res["mono"] = t.mono
                ok &= res["name_ok"] and res["folder_ok"] and res["color_ok"] and not res["errors"]
    return {"session": session, "dry_run": False, "plan": plan_to_dict(plan),
            "results": [t.result for f in plan for t in f.tracks], "ok": ok,
            "seconds": round(time.perf_counter() - t0, 2), "log": log}


def _stage(t: PlannedTrack, workdir: pathlib.Path) -> str:
    """The file to import: the original, or a mono version when requested and recommended."""
    if not t.mono:
        return t.file
    mono = stereo.to_mono(t.file, workdir)
    t.stereo_action = "converted" if mono else "kept (already mono or true stereo)"
    return mono or t.file
