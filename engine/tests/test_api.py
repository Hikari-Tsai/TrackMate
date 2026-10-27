import pytest
from fastapi.testclient import TestClient

from stem_engine.api import create_app
from stem_engine.engine import Engine

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(config):
    engine = Engine(config)  # empty home: no models, so only layers A and B
    return TestClient(create_app(engine, TOKEN), base_url="http://127.0.0.1")


def test_health_needs_no_token(client):
    assert client.get("/health").json()["status"] == "ok"


def test_token_required(client):
    assert client.get("/models").status_code == 401
    assert client.get("/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
    body = client.get("/models", headers=AUTH).json()
    assert body["layers"] == {"A": True, "B": True, "C": False, "D": False, "T": False}
    assert set(body["models"]) == {"qwen3_embedding", "peav_audio", "beat_this"}


def test_foreign_host_refused(config):
    c = TestClient(create_app(Engine(config), TOKEN), base_url="http://evil.example")
    assert c.get("/health").status_code == 403


def test_analyze(client, stems):
    r = client.post("/analyze", headers=AUTH, json={"files": [stems["Kick In_03.wav"], stems["Audio 7.wav"]]})
    assert r.status_code == 200
    tracks = r.json()["tracks"]
    assert tracks[0]["proposed_name"] == "Kick In" and tracks[0]["candidates"][0]["instrument"] == "kick_in"
    assert tracks[1]["category"] == "other"


def test_analyze_missing_file(client):
    r = client.post("/analyze", headers=AUTH, json={"files": ["/nope/x.wav"]})
    assert r.status_code == 404


def test_feedback_teaches_layer_a(client, stems, config):
    assert client.post("/feedback", headers=AUTH, json={"name": "Audio 7", "instrument": "nope"}).status_code == 404
    r = client.post("/feedback", headers=AUTH, json={"name": "Gtr Fuzz", "instrument": "electric_guitar"})
    assert r.json()["alias"] == "gtr fuzz"
    t = client.post("/analyze", headers=AUTH, json={"files": [stems["Gtr Fuzz.wav"]]}).json()["tracks"][0]
    assert (t["instrument"], t["stage"]) == ("electric_guitar", "A")
    assert config.user_aliases_path.exists()


def test_instruments_and_categories(client):
    inst = client.get("/instruments", headers=AUTH).json()
    assert len(inst["instruments"]) > 150
    cats = client.get("/categories", headers=AUTH).json()
    assert len(cats["palette"]) == 69 and cats["categories"]["drums"]["folder"] == "DRUMS"


def test_apply_validates_before_touching_pro_tools(client, stems):
    bad_file = {"tracks": [{"file": "/nope.wav", "name": "X", "category": "drums"}]}
    assert client.post("/apply", headers=AUTH, json=bad_file).status_code == 404
    bad_cat = {"tracks": [{"file": stems["OH.wav"], "name": "OH", "category": "kazoo"}]}
    assert client.post("/apply", headers=AUTH, json=bad_cat).status_code == 422
    bad_color = {"tracks": [{"file": stems["OH.wav"], "name": "OH", "category": "drums", "color_index": 99}]}
    assert client.post("/apply", headers=AUTH, json=bad_color).status_code == 422


def test_apply_without_pro_tools(client, stems, monkeypatch):
    from stem_engine import apply as apply_mod
    from stem_engine.protools import ProToolsUnavailable

    def offline(*a, **k):
        raise ProToolsUnavailable("not running")
    monkeypatch.setattr(apply_mod, "apply", offline)
    body = {"tracks": [{"file": stems["OH.wav"], "name": "OH", "category": "drums"}]}
    assert client.post("/apply", headers=AUTH, json=body).status_code == 503
