"""What the engine reports when Pro Tools or files are not there. Pro Tools "not running" is
simulated with a PTSL address nothing listens on, so the real Pro Tools is never touched."""
import socket
import time

import grpc
import pytest
from fastapi.testclient import TestClient

from stem_engine import apply as apply_mod
from stem_engine.api import create_app
from stem_engine.config import EngineConfig
from stem_engine.engine import Engine
from stem_engine.protools import (NoSession, ProToolsLost, ProToolsNotResponding, ProToolsUnavailable,
                                  call_with_timeout, is_connection_error)

AUTH = {"Authorization": "Bearer t"}


def closed_port() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{s.getsockname()[1]}"


@pytest.fixture
def offline(tmp_path):
    cfg = EngineConfig(home=tmp_path / "home", ptsl_address=closed_port())
    return TestClient(create_app(Engine(cfg), "t"), base_url="http://127.0.0.1")


class FakeRpcError(grpc.RpcError):
    def __init__(self, code):
        self._code = code

    def code(self):
        return self._code


def test_session_when_pro_tools_is_not_running(offline):
    t = time.perf_counter()
    r = offline.get("/session", headers=AUTH)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "pro_tools_not_running"
    assert time.perf_counter() - t < 5  # fails fast, no hanging request


def test_apply_when_pro_tools_is_not_running(offline, stems):
    body = {"tracks": [{"file": stems["OH.wav"], "name": "OH", "category": "drums"}]}
    for dry_run in (True, False):
        r = offline.post("/apply", headers=AUTH, json={**body, "dry_run": dry_run})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "pro_tools_not_running"


@pytest.mark.parametrize("exc, status, code", [
    (NoSession("none"), 409, "no_session"),
    (ProToolsNotResponding("busy"), 504, "pro_tools_not_responding"),
    (ProToolsLost("half done"), 503, "pro_tools_lost"),
])
def test_apply_error_codes(offline, stems, monkeypatch, exc, status, code):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(apply_mod, "apply", boom)
    r = offline.post("/apply", headers=AUTH, json={"tracks": [{"file": stems["OH.wav"], "name": "OH", "category": "drums"}]})
    assert r.status_code == status and r.json()["detail"]["code"] == code


def test_missing_files_are_listed(offline, stems):
    gone = "/nope/Kick.wav"
    r = offline.post("/apply", headers=AUTH, json={"tracks": [{"file": gone, "name": "Kick", "category": "drums"}]})
    assert r.status_code == 404
    assert r.json()["detail"] == {"code": "missing_files", "message": "Some files were moved or deleted.",
                                  "missing_files": [gone]}
    r = offline.post("/analyze", headers=AUTH, json={"files": [stems["OH.wav"], gone]})
    assert r.json()["detail"]["missing_files"] == [gone]


def test_connection_lost_before_and_after_changes(monkeypatch, tmp_path):
    def fails_at_start(*a):
        raise FakeRpcError(grpc.StatusCode.UNAVAILABLE)

    def fails_midway(requests, categories, palette, staging, dry, address, log):
        log.append("imported Kick.wav -> Kick")
        raise FakeRpcError(grpc.StatusCode.UNAVAILABLE)

    monkeypatch.setattr(apply_mod, "_apply", fails_at_start)
    with pytest.raises(ProToolsUnavailable) as e:
        apply_mod.apply([], {}, [], tmp_path)
    assert not isinstance(e.value, ProToolsLost)  # nothing was changed yet
    monkeypatch.setattr(apply_mod, "_apply", fails_midway)
    with pytest.raises(ProToolsLost, match="Kick"):
        apply_mod.apply([], {}, [], tmp_path)
    assert is_connection_error(FakeRpcError(grpc.StatusCode.UNAVAILABLE))
    assert not is_connection_error(FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT))


def test_slow_pro_tools_times_out():
    t = time.perf_counter()
    with pytest.raises(ProToolsNotResponding):
        call_with_timeout(lambda: time.sleep(5), 0.3, "test")
    assert time.perf_counter() - t < 2
    assert call_with_timeout(lambda: 42, 1, "test") == 42
    with pytest.raises(ValueError):
        call_with_timeout(lambda: int("x"), 1, "test")
