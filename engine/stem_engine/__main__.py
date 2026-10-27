"""Start the engine: `stem-engine [--port N] [--no-download]`.

Prints one JSON line {"port": ..., "token": ...} on stdout so the app can connect, and writes
the same to <home>/engine.json (mode 0600). A packaged engine without a console (Windows) has no
stdout: output then goes to <home>/engine.log and the app reads engine.json instead.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys

import uvicorn

from .api import create_app
from .config import EngineConfig
from .engine import Engine


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(prog="stem-engine")
    ap.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    ap.add_argument("--no-download", action="store_true", help="do not start model downloads")
    args = ap.parse_args()

    config = EngineConfig()
    config.home.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:  # windowed build: keep logging working
        log = open(config.home / "engine.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    engine = Engine(config)
    if not args.no_download:
        engine.models.start()
    port = args.port or free_port()
    token = secrets.token_urlsafe(32)
    info = json.dumps({"port": port, "token": token, "pid": os.getpid()})
    path = config.home / "engine.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(info)
    print(info, flush=True)
    uvicorn.run(create_app(engine, token), host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
