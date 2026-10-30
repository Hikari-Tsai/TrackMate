"""Model download and verification (README: Models): pinned Hugging Face revisions, resumable
downloads, SHA-256 checked while streaming, progress for GET /models.

Files land in <home>/models/<name>/<path>. A file is written as <path>.part and renamed only
after its checksum matches, so a present file is always a verified one.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass, field

import certifi

from .config import DATA_DIR

HF_URL = "https://huggingface.co/{repo}/resolve/{revision}/{path}"
CHUNK = 1 << 20
MANIFEST_PATH = DATA_DIR / "model_manifest.json"
# The packaged engine's Python has no system CA store (PyInstaller, python-build-standalone),
# so every download would fail with CERTIFICATE_VERIFY_FAILED: use certifi's bundle instead.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class ChecksumError(RuntimeError):
    pass


class DownloadInProgress(RuntimeError):
    """Raised by clear(): files being written are never deleted."""


@dataclass
class ModelStatus:
    name: str
    layer: str
    state: str = "missing"        # missing | downloading | ready | error
    bytes_done: int = 0
    bytes_total: int = 0
    current_file: str | None = None
    error: str | None = None
    started: float | None = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "started"}
        d["progress"] = round(self.bytes_done / self.bytes_total, 4) if self.bytes_total else 0.0
        d["size"] = self.bytes_total
        return d


@dataclass
class ModelSpec:
    name: str
    layer: str
    repo: str
    revision: str
    onnx: str
    files: dict[str, dict] = field(default_factory=dict)

    @property
    def total_size(self) -> int:
        return sum(f["size"] for f in self.files.values())


def load_manifest(path: pathlib.Path = MANIFEST_PATH) -> dict[str, ModelSpec]:
    raw = json.loads(path.read_text())
    return {name: ModelSpec(name=name, **spec) for name, spec in raw["models"].items()}


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class ModelManager:
    def __init__(self, models_dir: pathlib.Path, manifest: dict[str, ModelSpec] | None = None,
                 url_template: str = HF_URL):
        self.dir = models_dir
        self.specs = manifest or load_manifest()
        self.url_template = url_template
        self.status = {n: ModelStatus(n, s.layer, bytes_total=s.total_size) for n, s in self.specs.items()}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        for name in self.specs:
            if self._all_present(name):
                st = self.status[name]
                st.state, st.bytes_done = "ready", st.bytes_total

    # --------------------------------------------------------------- queries
    def model_dir(self, name: str) -> pathlib.Path:
        return self.dir / name

    def onnx_path(self, name: str) -> pathlib.Path:
        return self.model_dir(name) / self.specs[name].onnx

    def is_ready(self, name: str) -> bool:
        return self.status[name].state == "ready"

    def _all_present(self, name: str) -> bool:
        return all((self.model_dir(name) / p).exists() for p in self.specs[name].files)

    def summary(self) -> dict:
        """Per model: state, progress, size, bytes on disk (finished files and .part files)."""
        out = {}
        for n, s in self.status.items():
            d = s.to_dict()
            d["repo"] = self.specs[n].repo
            d["on_disk"] = self.on_disk(n)
            out[n] = d
        return out

    def on_disk(self, name: str) -> int:
        """Bytes the model takes now: verified files plus partial downloads."""
        d = self.model_dir(name)
        if not d.exists():
            return 0
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())

    def is_downloading(self) -> bool:
        with self._lock:
            return self._downloading_locked()

    def _downloading_locked(self) -> bool:
        return any(s.state == "downloading" for s in self.status.values()) or \
            any(t.is_alive() for t in self._threads.values())

    # ------------------------------------------------------------- download
    def start(self, names: list[str] | None = None) -> None:
        """Download in background threads; returns at once."""
        for name in names or list(self.specs):
            with self._lock:
                t = self._threads.get(name)
                if self.is_ready(name) or (t and t.is_alive()):
                    continue
                # Marked before the thread runs, so clear() can never slip in between.
                self.status[name].state = "downloading"
                t = threading.Thread(target=self.download, args=(name,), daemon=True, name=f"download-{name}")
                self._threads[name] = t
                t.start()

    def wait(self, timeout: float | None = None) -> None:
        for t in list(self._threads.values()):
            t.join(timeout)

    def download(self, name: str) -> None:
        spec, st = self.specs[name], self.status[name]
        st.state, st.error, st.started = "downloading", None, time.time()
        try:
            done_before = 0
            for path, meta in spec.files.items():
                st.current_file = path
                self._download_file(spec, path, meta, lambda n, base=done_before: setattr(st, "bytes_done", base + n))
                done_before += meta["size"]
                st.bytes_done = done_before
            st.state, st.current_file = "ready", None
        except Exception as exc:  # reported through GET /models; the .part file allows resuming
            st.state, st.error = "error", f"{type(exc).__name__}: {exc}"

    def _download_file(self, spec: ModelSpec, path: str, meta: dict, progress) -> None:
        target = self.model_dir(spec.name) / path
        if target.exists():
            progress(meta["size"])
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        h = hashlib.sha256()
        have = part.stat().st_size if part.exists() else 0
        if have > meta["size"]:
            part.unlink()
            have = 0
        if have:
            with open(part, "rb") as f:
                for block in iter(lambda: f.read(CHUNK), b""):
                    h.update(block)
        if have < meta["size"]:
            url = self.url_template.format(repo=spec.repo, revision=spec.revision, path=path)
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as resp:
                if have and resp.status != 206:  # server ignored the range: start over
                    have, h = 0, hashlib.sha256()
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        block = resp.read(CHUNK)
                        if not block:
                            break
                        f.write(block)
                        h.update(block)
                        have += len(block)
                        progress(have)
        if have != meta["size"] or h.hexdigest() != meta["sha256"]:
            part.unlink(missing_ok=True)
            raise ChecksumError(f"{path}: size {have} / sha256 {h.hexdigest()[:12]} does not match the manifest")
        part.replace(target)
        progress(meta["size"])

    def clear(self) -> int:
        """Deletes every model file (finished and partial) and returns the bytes freed.
        Refused with DownloadInProgress while any download runs: a file being written is
        never deleted."""
        with self._lock:
            if self._downloading_locked():
                raise DownloadInProgress("a model is still downloading")
            freed = 0
            for name in self.specs:
                freed += self.on_disk(name)
                d = self.model_dir(name)
                if d.exists():
                    shutil.rmtree(d)
                st = self.status[name]
                st.state, st.bytes_done, st.current_file, st.error, st.started = "missing", 0, None, None, None
            self._threads.clear()
            return freed

    def verify(self, name: str) -> bool:
        """Full re-hash of every file (used by tests and on demand)."""
        spec = self.specs[name]
        return all(sha256_of(self.model_dir(name) / p) == m["sha256"] for p, m in spec.files.items())
