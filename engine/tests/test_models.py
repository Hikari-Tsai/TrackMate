import hashlib
import http.server
import threading

import pytest

from stem_engine.models import DownloadInProgress, ModelManager, ModelSpec

PAYLOAD = bytes(range(256)) * 4096  # 1 MiB


class RangeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        data = PAYLOAD if self.path.endswith("model.bin") else b"not found"
        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/{{repo}}/{{revision}}/{{path}}"
    srv.shutdown()


def spec(sha=None):
    return {"tiny": ModelSpec("tiny", "C", "me/tiny", "abc", "model.bin",
                              {"model.bin": {"size": len(PAYLOAD), "sha256": sha or hashlib.sha256(PAYLOAD).hexdigest()}})}


def test_download_and_verify(tmp_path, server):
    m = ModelManager(tmp_path, spec(), url_template=server)
    assert m.status["tiny"].state == "missing"
    m.download("tiny")
    assert m.is_ready("tiny") and m.verify("tiny")
    assert m.summary()["tiny"]["progress"] == 1.0
    assert ModelManager(tmp_path, spec(), url_template=server).is_ready("tiny")  # found on restart


def test_resume_from_partial_file(tmp_path, server):
    part = tmp_path / "tiny" / "model.bin.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(PAYLOAD[:300_000])
    m = ModelManager(tmp_path, spec(), url_template=server)
    m.download("tiny")
    assert m.is_ready("tiny") and (tmp_path / "tiny" / "model.bin").read_bytes() == PAYLOAD


def test_checksum_mismatch_is_an_error(tmp_path, server):
    m = ModelManager(tmp_path, spec(sha="0" * 64), url_template=server)
    m.download("tiny")
    st = m.status["tiny"]
    assert st.state == "error" and "sha256" in st.error
    assert not (tmp_path / "tiny" / "model.bin").exists()
    assert not (tmp_path / "tiny" / "model.bin.part").exists()


def test_clear_frees_the_files_and_resets_the_state(tmp_path, server):
    m = ModelManager(tmp_path, spec(), url_template=server)
    m.download("tiny")
    assert m.summary()["tiny"]["on_disk"] == len(PAYLOAD) == m.summary()["tiny"]["size"]
    assert m.clear() == len(PAYLOAD)
    assert not (tmp_path / "tiny").exists()
    st = m.summary()["tiny"]
    assert (st["state"], st["bytes_done"], st["progress"], st["on_disk"]) == ("missing", 0, 0.0, 0)
    m.download("tiny")  # downloads again after a clear
    assert m.is_ready("tiny")


def test_clear_is_refused_while_downloading(tmp_path, server):
    release = threading.Event()

    class SlowManager(ModelManager):
        def download(self, name):
            release.wait(5)
            super().download(name)

    slow = SlowManager(tmp_path, spec(), url_template=server)
    slow.start(["tiny"])
    assert slow.status["tiny"].state == "downloading"  # marked before the thread does anything
    with pytest.raises(DownloadInProgress):
        slow.clear()
    release.set()
    slow.wait(10)
    assert slow.is_ready("tiny")  # the refused clear deleted nothing
    assert slow.clear() == len(PAYLOAD)
