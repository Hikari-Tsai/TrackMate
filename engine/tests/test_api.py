import pytest
from fastapi.testclient import TestClient

from stem_engine.api import create_app
from stem_engine.engine import Engine

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def engine(config):
    return Engine(config)  # empty home: no models, so only layers A and B


@pytest.fixture
def client(engine):
    return TestClient(create_app(engine, TOKEN), base_url="http://127.0.0.1")


def test_health_needs_no_token(client):
    assert client.get("/health").json()["status"] == "ok"


def test_token_required(client):
    assert client.get("/models").status_code == 401
    assert client.get("/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
    body = client.get("/models", headers=AUTH).json()
    assert body["layers"] == {"A": True, "B": True, "C": False, "D": False, "T": False}
    assert set(body["models"]) == {"qwen3_embedding", "peav_audio", "beat_this"}


def test_models_report_size_and_disk_use(client):
    body = client.get("/models", headers=AUTH).json()
    m = body["models"]["beat_this"]
    assert m["state"] == "missing" and m["size"] > 80_000_000 and m["on_disk"] == 0
    assert m["repo"].startswith("aaatmy/") and body["dir"].endswith("models")
    assert sum(v["size"] for v in body["models"].values()) > 1_400_000_000


def test_clear_models_deletes_files_and_resets_state(client, config):
    # Nothing on disk yet: allowed, frees nothing.
    assert client.delete("/models", headers=AUTH).json()["freed_bytes"] == 0
    # A finished file and a partial one, as left by an interrupted download.
    d = config.models_dir / "beat_this"
    d.mkdir(parents=True)
    (d / "frontend.json").write_bytes(b"x" * 1000)
    (d / "beat-this-final0.onnx.part").write_bytes(b"y" * 5000)
    assert client.get("/models", headers=AUTH).json()["models"]["beat_this"]["on_disk"] == 6000
    res = client.delete("/models", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["freed_bytes"] == 6000 and not d.exists()
    assert body["models"]["beat_this"]["state"] == "missing" and body["models"]["beat_this"]["on_disk"] == 0
    assert body["layers"]["T"] is False


def test_clear_models_refused_while_downloading(client, engine):
    # Marked as downloading, as start() does before its thread runs.
    engine.models.status["peav_audio"].state = "downloading"
    res = client.delete("/models", headers=AUTH)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "models_downloading"
    engine.models.status["peav_audio"].state = "missing"
    assert client.delete("/models", headers=AUTH).status_code == 200


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
