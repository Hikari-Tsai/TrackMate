import pytest

from stem_engine.names import clean, prepare, prepare_batch, tokenize


@pytest.mark.parametrize("raw, expected", [
    ("Kick In_03.wav", "Kick In"),
    ("Snare.dup1", "Snare"),
    ("Lead Vox.1", "Lead Vox"),
    ("Pad 120bpm C min.wav", "Pad"),
    ("ＢＡＳＳ.aif", "BASS"),
])
def test_clean(raw, expected):
    assert " ".join(clean(raw)[0].split()) == expected


@pytest.mark.parametrize("raw, rest, tail", [
    ("LV2-CVox_04-01.wav", "LV2", "-CVox_04-01"),      # take 04, clip 01, AudioSuite-style tag
    ("Kick In_03-01.wav", "Kick In", "_03-01"),
    ("Gtr DI-AudSt_01.wav", "Gtr DI", "-AudSt_01"),
    ("Bass DI.04_09.wav", "Bass DI", ".04_09"),
    ("Snare.dup1.wav", "Snare", ".dup1"),
    ("Vox-Lead_01.wav", "Vox-Lead", "_01"),             # known word: not an AudioSuite tag
    ("Gtr-Fuzz.wav", "Gtr-Fuzz", ""),                   # no take number: nothing to remove
    ("BV 2_06-03.wav", "BV 2", "_06-03"),               # single digit instance number stays
])
def test_daw_tail(raw, rest, tail):
    known = {"lead", "vox", "fuzz"}
    assert clean(raw, is_known=lambda t: t in known) == (rest, tail)


@pytest.mark.parametrize("raw, tokens", [
    ("SnareTop2", ["snare", "top", "2"]),
    ("SNRTop", ["snr", "top"]),
    ("BGVs", ["bgvs"]),
    ("貝斯di", ["貝斯", "di"]),
    ("Gtr(L)", ["gtr", "l"]),
])
def test_tokenize(raw, tokens):
    assert [t.text for t in tokenize(raw)] == tokens


def test_batch_strips_song_title_and_track_suffix():
    names = prepare_batch(["ai-kotoba(cho)_Track1.wav", "ai-kotoba(Gt)_Track2.wav", "ai-kotoba(Ba)_Track3.wav"])
    assert [n.text for n in names] == ["cho", "gt", "ba"]
    assert names[0].stripped_prefix == ["ai", "kotoba"]


def test_batch_keeps_known_words_and_numbers():
    names = prepare_batch(["Tom 1.wav", "Tom 2.wav", "Tom 3.wav"], is_known=lambda t: t == "tom")
    assert [n.text for n in names] == ["tom 1", "tom 2", "tom 3"]


def test_small_batch_is_not_stripped():
    names = prepare_batch(["Song Kick.wav", "Song Snare.wav"])
    assert names[0].text == "song kick"


@pytest.mark.parametrize("raw, default", [
    ("Audio 7.wav", True), ("Track 05", True), ("Untitled", True), ("オーディオ 3", True),
    ("808", False), ("Kick", False),
])
def test_daw_default(raw, default):
    assert prepare(raw).is_daw_default is default
