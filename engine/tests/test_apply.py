import json

from stem_engine.apply import build_plan, clean_name, unique
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
