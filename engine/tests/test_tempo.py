import struct

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import DEV_HOME
from stem_engine import tempo as T
from stem_engine.api import create_app
from stem_engine.config import EngineConfig
from stem_engine.engine import Engine

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def read_midi(data: bytes) -> dict:
    """Independent reader for the tempo files: tempo events, time signature, track length."""
    assert data[:4] == b"MThd"
    _, fmt, ntracks, ppq = struct.unpack(">IHHH", data[4:14])
    assert (fmt, ntracks) == (0, 1) and data[14:18] == b"MTrk"
    (length,) = struct.unpack(">I", data[18:22])
    body, i, tick, out = data[22:22 + length], 0, 0, {"ppq": ppq, "tempos": [], "signature": None}
    while i < len(body):
        delta = 0
        while True:
            delta = (delta << 7) | (body[i] & 0x7F)
            i += 1
            if not body[i - 1] & 0x80:
                break
        tick += delta
        assert body[i] == 0xFF
        kind, size = body[i + 1], body[i + 2]
        payload = body[i + 3:i + 3 + size]
        i += 3 + size
        if kind == 0x51:
            out["tempos"].append((tick, int.from_bytes(payload, "big")))
        elif kind == 0x58:
            out["signature"] = (payload[0], 2 ** payload[1])
        elif kind == 0x2F:
            out["end"] = tick
    return out


def seconds_at(tempos: list[tuple[int, int]], ppq: int, tick: int) -> float:
    s = 0.0
    for k, (t, us) in enumerate(tempos):
        nxt = tempos[k + 1][0] if k + 1 < len(tempos) else None
        if nxt is None or tick <= nxt:
            return s + (tick - t) * us / ppq / 1e6
        s += (nxt - t) * us / ppq / 1e6
    raise AssertionError


def grid(bpm: float, n: int, start: float = 0.5) -> np.ndarray:
    return start + np.arange(n) * 60 / bpm


def test_pick_sources():
    tracks = [{"file": "k", "category": "drums"}, {"file": "b", "category": "bass"},
              {"file": "v", "category": "lead_vocals"}, {"file": "p", "category": "percussion"}]
    assert T.pick_sources(tracks) == ("drums", ["k", "p"])
    assert T.pick_sources(tracks[1:3]) == ("rhythm", ["b"])
    assert T.pick_sources(tracks[2:3]) == ("all", ["v"])


def test_peaks_are_refined_between_frames():
    logits = np.full(200, -5.0)
    for centre in (40.3, 90.0, 150.7):   # a smooth peak around each true position
        x = np.arange(200)
        logits = np.maximum(logits, 4 - 2 * (x - centre) ** 2)
    assert np.allclose(T.peaks(logits) * T.FPS, [40.3, 90.0, 150.7], atol=0.05)


def test_regularize_drops_double_time_and_fills_gaps():
    beats = grid(100, 40)
    doubled = np.sort(np.concatenate([beats, (beats[:8] + beats[1:9]) / 2]))   # double-time intro
    gapped = np.delete(doubled, range(30, 36))                                  # stems pause
    out, downs = T.regularize(gapped, beats[::4])
    assert np.allclose(out, beats)
    assert np.allclose(downs, beats[::4])


def test_analyse_steady_and_variable():
    rng = np.random.default_rng(1)
    steady = grid(97, 200) + rng.uniform(-0.01, 0.01, 200)   # 20 ms frame jitter
    a = T.analyse(steady, steady[::4])
    assert a["steady"] and a["suggested_mode"] == "constant" and a["bpm_rounded"] == 97
    assert a["signature_beats"] == 4
    speeding = np.concatenate([grid(80, 64), grid(80, 64)[-1] + 0.75 + np.arange(64) * 60 / 110])
    v = T.analyse(speeding, speeding[::4])
    assert not v["steady"] and v["suggested_mode"] == "variable"
    assert v["bpm_min"] == pytest.approx(80, abs=0.5) and v["bpm_max"] == pytest.approx(110, abs=0.5)
    with pytest.raises(T.NoBeats):
        T.analyse(grid(120, 4), [])


def test_constant_midi():
    events = T.tempo_events(grid(97, 100), [], "constant", 97)
    midi = read_midi(T.tempo_midi(events, 180.0, 3))
    assert midi["tempos"] == [(0, round(60e6 / 97))] and midi["signature"] == (3, 4)
    assert seconds_at(midi["tempos"], midi["ppq"], midi["end"]) == pytest.approx(180.0, abs=0.01)
    with pytest.raises(ValueError):
        T.tempo_events(grid(97, 100), [], "constant", None)


def test_variable_midi_puts_every_bar_line_on_its_detected_time():
    beats = np.concatenate([grid(80, 33, 1.2), grid(80, 33, 1.2)[-1] + np.cumsum(np.full(40, 60 / 96))])
    downs = beats[::4]
    events = T.tempo_events(beats, downs, "variable")
    midi = read_midi(T.tempo_midi(events, beats[-1] + 2, 4))
    first_tick = round(beats[0] * 1e6 * T.PPQ / events[0][1])
    for k in range(0, len(beats), 4):
        assert seconds_at(midi["tempos"], midi["ppq"], first_tick + k * T.PPQ) == pytest.approx(beats[k], abs=0.002)
    bpms = sorted({round(60e6 / us) for _, us in midi["tempos"]})
    assert bpms == [80, 96]
    assert T.quarters_at(events, beats[40]) == pytest.approx(first_tick / T.PPQ + 40, abs=1e-3)


def test_make_tempo_half_and_double():
    beats = list(grid(90, 64))
    ev, per_bar, avg, check = T.make_tempo(beats, beats[::4], 50, "variable", None, 2, 4)
    assert per_bar == 4 and avg == pytest.approx(180, abs=0.01)   # meter is not kept when the beat changes
    _, _, avg, _ = T.make_tempo(beats, beats[::4], 50, "variable", None, 0.5, 4)
    assert avg == pytest.approx(45, abs=0.01)
    _, per_bar, avg, check = T.make_tempo(beats, beats[::3], 50, "constant", 90, 1, 3)
    assert (per_bar, avg, check) == (3, 90, pytest.approx(beats[-1]))


def test_parse_bars_beats():
    assert T.parse_bars_beats("   25| 2| 000", 4) == 97
    assert T.parse_bars_beats("    1| 1| 480", 3) == 0.5


@pytest.fixture
def client(config):
    return TestClient(create_app(Engine(config), TOKEN), base_url="http://127.0.0.1")


def test_tempo_needs_the_model(client, stems):
    r = client.post("/tempo", headers=AUTH, json={"tracks": [{"file": stems["Kick In_03.wav"], "category": "drums"}]})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "tempo_model_not_ready"
    r = client.post("/tempo", headers=AUTH, json={"tracks": [{"file": "/nope.wav", "category": "drums"}]})
    assert r.status_code == 404


def test_tempo_apply_writes_midi_without_pro_tools(client, tmp_path):
    beats = list(grid(120, 40))
    body = {"beats": beats, "downbeats": beats[::4], "duration": 25, "mode": "constant", "bpm": 120,
            "signature_beats": 4, "folder": str(tmp_path / "out"), "import_to_pro_tools": False}
    r = client.post("/tempo/apply", headers=AUTH, json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["midi_path"].endswith("TrackMate Tempo 120 BPM.mid") and res["imported"] is False
    assert read_midi(open(res["midi_path"], "rb").read())["tempos"] == [(0, 500000)]
    r = client.post("/tempo/apply", headers=AUTH, json={**body, "bpm": None})
    assert r.json()["detail"]["code"] == "bpm_required"


def test_tempo_apply_when_pro_tools_is_not_running(tmp_path):
    from test_errors import closed_port
    cfg = EngineConfig(home=tmp_path / "home", ptsl_address=closed_port())
    c = TestClient(create_app(Engine(cfg), TOKEN), base_url="http://127.0.0.1")
    beats = list(grid(120, 40))
    r = c.post("/tempo/apply", headers=AUTH, json={"beats": beats, "duration": 25, "mode": "variable"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "pro_tools_not_running"


def test_tempo_apply_reports_the_verification(client, monkeypatch):
    seen = {}

    def fake_import(midi, events, per_bar, check, address):
        seen.update(midi=midi, check=check, per_bar=per_bar)
        return {"applied": True, "pro_tools_position": "25| 2| 000"}
    monkeypatch.setattr(T, "import_to_pro_tools", fake_import)
    beats = list(grid(97, 40))
    r = client.post("/tempo/apply", headers=AUTH, json={"beats": beats, "duration": 30, "mode": "constant", "bpm": 97})
    assert r.json()["applied"] is True and r.json()["imported"] is True
    assert seen["midi"].parent.name == "tempo" and seen["per_bar"] == 4 and seen["check"] == pytest.approx(beats[-1])


@pytest.mark.skipif(not (DEV_HOME / "models" / "beat_this" / "beat-this-final0.onnx").exists(),
                    reason="models not downloaded (set STEM_ENGINE_DEV_HOME)")
def test_detects_a_drum_pattern(tmp_path):
    """Kick, snare and hi-hat at 112 BPM, with a silent bar in the middle."""
    sr, bpm, bars = 44100, 112, 24
    beat = int(round(60 / bpm * sr))
    x = np.zeros(bars * 4 * beat, dtype=np.float32)
    rng = np.random.default_rng(0)
    t = np.arange(int(0.25 * sr)) / sr
    kick = (np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)).astype(np.float32)
    snare = (rng.normal(0, 0.5, len(t)) * np.exp(-t * 25)).astype(np.float32)
    hat = (rng.normal(0, 0.2, len(t) // 4) * np.exp(-t[:len(t) // 4] * 80)).astype(np.float32)
    for b in range(bars * 4):
        if 12 * 4 <= b < 13 * 4:
            continue
        p = b * beat
        x[p:p + len(kick)] += kick * (0.8 if b % 2 == 0 else 0)
        x[p:p + len(snare)] += snare * (0.6 if b % 2 else 0)
        for h in (0, beat // 2):
            x[p + h:p + h + len(hat)] += hat
    sf.write(tmp_path / "drums.wav", x * 0.5, sr)
    sf.write(tmp_path / "vox.wav", np.zeros(len(x), dtype=np.float32), sr)
    c = TestClient(create_app(Engine(EngineConfig(home=DEV_HOME)), TOKEN), base_url="http://127.0.0.1")
    r = c.post("/tempo", headers=AUTH, json={"tracks": [{"file": str(tmp_path / "drums.wav"), "category": "drums"},
                                                        {"file": str(tmp_path / "vox.wav"), "category": "lead_vocals"}]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["source_kind"] == "drums" and res["sources"] == [str(tmp_path / "drums.wav")]
    assert res["bpm_rounded"] == bpm and res["suggested_mode"] == "constant"
