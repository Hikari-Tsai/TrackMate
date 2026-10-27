import pytest

from stem_engine.config import Thresholds
from stem_engine.names import prepare
from stem_engine.textmatch import fuzzy_match, parse


@pytest.mark.parametrize("name, inst, mods, number", [
    ("Kick In_03.wav", "kick_in", [], None),
    ("Snr Top 2", "snare_top", [], "2"),
    ("OH L", "overhead", ["L"], None),
    ("Piano Room", "piano", ["Room"], None),         # soft word next to an instrument -> modifier
    ("Room", "drum_room", [], None),                  # alone -> instrument
    ("Bass Drum", "kick", [], None),                  # longest phrase wins
    ("Chorus Vox", "backing_vocal", [], None),        # ambiguous_terms rule
    ("鋼琴.wav", "piano", [], None),
    ("吉他左", "guitar", ["L"], None),
    ("貝斯di", "bass", ["DI"], None),
    ("Gtr Fuzz", "guitar", ["Fuzz"], None),          # non-placement modifiers keep their spelling
    ("MMO", "mmo", [], None),                         # minus-one deliverables
    ("MySong_MMA_04-01", "mma", [], None),
    ("MMM 2", "mmm", [], "2"),
    ("Mmm Vox", "oohs_aahs", [], None),               # next to a vocal word: humming
])
def test_parse(kb, name, inst, mods, number):
    r = parse(prepare(name), kb)
    assert r.instrument == inst
    assert [m.display for m in r.modifiers] == mods
    assert r.number == number


def test_one_letter_code_only_alone(kb):
    assert parse(prepare("Song Final v3"), kb).instrument is None
    assert parse(prepare("V"), kb).instrument == "vocal"


def test_lead_alone_is_not_an_instrument(kb):
    r = parse(prepare("Lead"), kb)
    assert r.instrument is None and [m.display for m in r.modifiers] == ["Lead"]


def test_ambiguous_keeps_name_order(kb):
    r = parse(prepare("Mellotron Flutes"), kb)
    assert r.instrument is None and r.ambiguous[0] == "mellotron"


def test_unknown_words_are_kept(kb):
    assert parse(prepare("Kick Weird"), kb).unknown == ["Weird"]


def test_user_alias_wins(tmp_path, kb):
    from stem_engine.config import default_kb_path
    from stem_engine.kb import KnowledgeBase
    k = KnowledgeBase(default_kb_path(), tmp_path / "aliases.json")
    k.add_user_alias("Zorp", "synth_pad")
    assert parse(prepare("Zorp 2"), k).instrument == "synth_pad"
    # persisted for the next start
    assert parse(prepare("Zorp"), KnowledgeBase(default_kb_path(), tmp_path / "aliases.json")).instrument == "synth_pad"


def test_fuzzy_needs_similar_length(kb):
    th = Thresholds()
    p = prepare("Ai Kotoba")
    assert fuzzy_match(parse(p, kb), p, kb, th) is None
