import json
import pathlib

from stem_engine.apply import build_plan, clean_name, plan_to_dict, unique
from stem_engine.protools import TrackInfo
from stem_engine.config import DATA_DIR

CATEGORIES = json.loads((DATA_DIR / "categories.json").read_text())["categories"]


def req(name, category, **kw):
    return {"file": f"/x/{name}.wav", "name": name, "category": category, **kw}


def test_folders_follow_category_order_and_keep_track_order():
    plan = build_plan([req("Piano", "keys"), req("Snare Top", "drums"), req("Kick In", "drums")], CATEGORIES, [])
    assert [f.name for f in plan] == ["DRUMS", "KEYS"]
    assert [t.final_name for t in plan[0].tracks] == ["Snare Top", "Kick In"]
    assert plan[0].color_index == CATEGORIES["drums"]["color_index"]


def test_names_unique_against_session_and_batch():
    existing = [{"name": "Kick In", "type": "AudioTrack", "folder": None}]
    plan = build_plan([req("Kick In", "drums"), req("Kick In", "drums"), req("kick in 2", "drums")],
                      CATEGORIES, existing)
    assert [t.final_name for t in plan[0].tracks] == ["Kick In 2", "Kick In 3", "kick in 2"]


def test_existing_folder_is_reused_and_taken_name_avoided():
    existing = [{"name": "DRUMS", "type": "BasicFolder", "folder": None},
                {"name": "KEYS", "type": "AudioTrack", "folder": None}]
    plan = build_plan([req("Kick", "drums"), req("Piano", "keys")], CATEGORIES, existing)
    assert (plan[0].name, plan[0].exists) == ("DRUMS", True)
    assert (plan[1].name, plan[1].exists) == ("KEYS 2", False)


def test_a_taken_folder_name_makes_one_new_folder_for_the_category():
    # "KEYS" is an audio track: both keys stems go into the single new folder "KEYS 2".
    existing = [{"name": "KEYS", "type": "AudioTrack", "folder": None}]
    plan = build_plan([req("Piano", "keys"), req("Rhodes", "keys")], CATEGORIES, existing)
    assert [(f.name, f.exists, [t.final_name for t in f.tracks]) for f in plan] == [("KEYS 2", False, ["Piano", "Rhodes"])]


def test_new_folder_is_created_even_when_one_of_that_name_exists():
    existing = [{"name": "DRUMS", "type": "BasicFolder", "folder": None},
                {"name": "DRUMS 2", "type": "AudioTrack", "folder": None}]
    plan = build_plan([req("Kick", "drums", new_folder=True), req("Snare", "drums", new_folder=True),
                       req("Bass DI", "bass")], CATEGORIES, existing)
    assert [(f.name, f.exists) for f in plan] == [("DRUMS 3", False), ("BASS", False)]
    assert [t.folder for t in plan[0].tracks] == ["DRUMS 3", "DRUMS 3"]
    # Without the flag the existing folder is joined, as before.
    plan = build_plan([req("Kick", "drums")], CATEGORIES, existing)
    assert (plan[0].name, plan[0].exists) == ("DRUMS", True)


def test_categories_can_join_one_existing_folder_of_another_name():
    existing = [{"name": "RHYTHM", "type": "BasicFolder", "folder": None}]
    plan = build_plan([req("Kick", "drums", folder="RHYTHM"), req("Bass DI", "bass", folder="RHYTHM"),
                       req("Piano", "keys")], CATEGORIES, existing)
    assert [(f.name, f.exists, len(f.tracks)) for f in plan] == [("RHYTHM", True, 2), ("KEYS", False, 1)]
    assert plan[0].category == "drums"  # the first category to land there


def test_overrides_and_other():
    plan = build_plan([req("Thing", "other"), req("Pad", "synths", color_index=40, folder="Pads", mono=True)],
                      CATEGORIES, [])
    synth = next(f for f in plan if f.category == "synths")
    assert (synth.name, synth.tracks[0].color_index, synth.tracks[0].mono) == ("Pads", 40, True)
    assert plan[-1].name == "OTHER"


def test_clean_name():
    assert clean_name('Gtr "Fuzz" / L?') == "Gtr _Fuzz_ _ L_"
    assert len(clean_name("x" * 80)) == 31
    assert unique("A", {"a"}) == "A"
    assert unique("A", {"A", "A 2"}) == "A 3"


def test_no_folder_tracks_form_one_top_level_group():
    existing = [{"name": "Kick", "type": "Audio", "folder": None}]
    plan = build_plan([req("Kick", "drums", no_folder=True), req("Snare", "drums"), req("Bass DI", "bass", no_folder=True),
                       req("Piano", "keys")], CATEGORIES, existing)
    assert [(f.name, f.exists, [t.final_name for t in f.tracks]) for f in plan] == [
        (None, True, ["Kick 2", "Bass DI"]), ("DRUMS", False, ["Snare"]), ("KEYS", False, ["Piano"])]
    assert all(t.folder is None for t in plan[0].tracks)
    assert plan_to_dict(plan)[0]["folder"] is None


class FakePro:
    """Enough of ProTools for the apply loop: a track list where an import adds a track after
    the selected one (inside a selected folder), or at the end when nothing is selected."""

    def __init__(self, tracks):
        self.tracks_ = list(tracks)
        self.selected = None
        self.log = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def session(self):
        return {"name": "S", "path": "/s/S.ptx", "sample_rate": 48000}

    def tracks(self):
        return [TrackInfo(t.id, t.name, i, t.type, t.format, t.color, t.folder, t.has_clips) for i, t in enumerate(self.tracks_)]

    def create_folder(self, name):
        self.tracks_.append(TrackInfo(f"id{len(self.log)}", name, 0, "BasicFolder", "Stereo", "#000000", None, False))
        self.log.append(f"folder {name}")
        return name

    def select(self, names):
        self.selected = names[0]
        self.log.append(f"select {names[0]}")

    def deselect(self):
        self.selected = None
        self.log.append("deselect")

    def import_audio(self, path, session_path):
        new = TrackInfo(f"id{len(self.log)}", pathlib.Path(path).stem, 0, "Audio", "Mono", "#000000", None, True)
        if self.selected is None:
            self.tracks_.append(new)
        else:
            at = next(i for i, t in enumerate(self.tracks_) if t.name == self.selected)
            anchor = self.tracks_[at]
            if anchor.type == "BasicFolder":
                new.folder = anchor.name
                members = [i for i, t in enumerate(self.tracks_) if t.folder == anchor.name]
                at = members[-1] if members else at
            else:
                new.folder = anchor.folder
            self.tracks_.insert(at + 1, new)
        self.log.append(f"import {new.name} -> {new.folder}")

    def rename(self, track_id, current, new):
        next(t for t in self.tracks_ if t.id == track_id).name = new

    def set_color(self, names, color_index):
        for t in self.tracks_:
            if t.name in names:
                t.color = PALETTE[color_index - 1]
        return len(names)


PALETTE = [f"#{i:06X}" for i in range(1, 70)]


def test_apply_puts_no_folder_tracks_after_the_last_loose_track(monkeypatch, tmp_path):
    from stem_engine import apply as apply_mod
    from stem_engine.protools import TrackInfo as TI
    session = [TI("a", "Click", 0, "Audio", "Mono", "#000000", None, True),
               TI("b", "OLD", 1, "BasicFolder", "Stereo", "#000000", None, False),
               TI("c", "Guide", 2, "Audio", "Mono", "#000000", "OLD", True)]
    pro = FakePro(session)
    monkeypatch.setattr(apply_mod, "ProTools", lambda address: pro)
    out = apply_mod.apply([req("Kick", "drums", no_folder=True), req("Bass DI", "bass", no_folder=True),
                           req("Piano", "keys")], CATEGORIES, PALETTE, tmp_path)
    assert out["ok"], out["results"]
    # Kick after Click (the last top-level track), Bass after Kick, Piano inside the new KEYS folder.
    assert [(t.name, t.folder) for t in pro.tracks_] == [
        ("Click", None), ("Kick", None), ("Bass DI", None), ("OLD", None), ("Guide", "OLD"), ("KEYS", None), ("Piano", "KEYS")]
    assert pro.log[:4] == ["select Click", "import Kick -> None", "select Kick", "import Bass DI -> None"]
    assert all(r["folder_ok"] for r in out["results"])


def test_apply_with_no_loose_track_imports_with_nothing_selected(monkeypatch, tmp_path):
    from stem_engine import apply as apply_mod
    pro = FakePro([])
    monkeypatch.setattr(apply_mod, "ProTools", lambda address: pro)
    out = apply_mod.apply([req("Kick", "drums", no_folder=True)], CATEGORIES, PALETTE, tmp_path)
    assert out["ok"] and pro.log == ["deselect", "import Kick -> None"]
    assert out["results"][0]["folder"] is None and out["results"][0]["folder_ok"]
