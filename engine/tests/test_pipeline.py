import os

import pytest

from stem_engine.audio import DResult
from stem_engine.embed import CResult
from stem_engine.names import prepare
from stem_engine.pipeline import Analyzer
from stem_engine.textmatch import parse

from conftest import DEV_HOME


def c_result(*top, none=0.5):
    top = list(top)
    return CResult(top, top[0][1], top[0][1] - (top[1][1] if len(top) > 1 else 0.0), none)


def d_result(category, prob, instrument=None):
    return DResult([(category, prob)], {category: prob}, category, instrument, prob, 1)


@pytest.fixture
def analyzer(kb):
    return Analyzer(kb)


def test_text_only_results(analyzer, stems):
    res = {r["original_name"]: r for r in analyzer.analyze(list(stems.values()), audio="none")}
    kick = res["Kick In_03"]
    assert (kick["proposed_name"], kick["category"], kick["confidence"], kick["stage"]) == \
        ("Kick In", "drums", "high", "A")
    assert kick["color"].startswith("#") and kick["folder"] == "DRUMS"
    assert kick["stereo"]["type"] == "mono_file"
    assert res["OH"]["stereo"]["action"] == "downmix"           # identical channels -> fake stereo
    assert res["鋼琴"]["proposed_name"] == "Piano"
    assert res["Gtr Fuzz"]["proposed_name"] == "Guitar Fuzz"
    other = res["Audio 7"]                                        # DAW default, no audio layer
    assert (other["category"], other["proposed_name"], other["needs_review"]) == ("other", "Audio 7", True)


def test_c_high_is_adopted(analyzer):
    d = analyzer._decide(parse(prepare("Kikk"), analyzer.kb), None, c_result(("kick", 0.92), ("snare", 0.7)), None)
    assert (d.instrument, d.stage, d.confidence) == ("kick", "C", "medium")


def test_c_gray_needs_audio_agreement(analyzer):
    r = parse(prepare("Zzz"), analyzer.kb)
    c = c_result(("synth_pad", 0.75), ("strings", 0.74), ("organ", 0.7))
    assert analyzer._decide(r, None, c, None).confidence == "low"
    agree = analyzer._decide(r, None, c, d_result("synths", 0.4, "synth"))
    assert (agree.instrument, agree.stage, agree.confidence) == ("synth_pad", "C+D", "medium")
    pick = analyzer._decide(r, None, c, d_result("strings", 0.4, "strings"))
    assert (pick.instrument, pick.confidence) == ("strings", "low")


def test_near_none_anchor_goes_to_audio(analyzer):
    r = parse(prepare("Session Idea"), analyzer.kb)
    c = c_result(("synth_pad", 0.80), ("strings", 0.7), none=0.85)
    assert analyzer._decide(r, None, c, None).category == "other"
    d = analyzer._decide(r, None, c, d_result("keys", 0.3, "keys"))
    assert (d.instrument, d.stage) == ("keys", "D")


def test_family_word_refined_by_embedding(analyzer):
    r = parse(prepare("Synthesized Bass"), analyzer.kb)
    d = analyzer._decide(r, None, c_result(("synth_bass", 0.8), ("bass", 0.78)), None)
    assert (d.instrument, d.stage) == ("synth_bass", "A+C")


def test_name_keeps_modifiers_and_number(analyzer):
    r = parse(prepare("Snare Btm 2"), analyzer.kb)
    d = analyzer._decide(r, None, None, None)
    assert analyzer._name(prepare("Snare Btm 2"), r, d) == "Snare Bottom 2"


@pytest.mark.skipif(not (DEV_HOME / "models" / "peav_audio" / "onnx" / "model_q8.onnx").exists(),
                    reason="models not downloaded (set STEM_ENGINE_DEV_HOME)")
def test_full_engine_with_models(stems, tmp_path):
    from stem_engine.config import EngineConfig
    from stem_engine.engine import Engine
    os.environ.pop("STEM_ENGINE_HOME", None)
    cfg = EngineConfig(home=DEV_HOME)
    engine = Engine(cfg)
    assert engine.layers() == {"A": True, "B": True, "C": True, "D": True}
    res = {r["original_name"]: r for r in engine.analyzer().analyze(list(stems.values()), audio="auto")}
    assert res["Kick In_03"]["layers"]["audio"] is None             # settled by text, no audio run
    assert res["Audio 7"]["layers"]["audio"] is not None            # DAW default -> audio layer
    assert len(res["Audio 7"]["candidates"]) >= 1
