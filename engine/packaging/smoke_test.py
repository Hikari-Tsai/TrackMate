"""Start a built engine and check that it serves the API (used by CI after packaging).

Usage: python packaging/smoke_test.py dist/stem-engine/stem-engine[.exe]
Starts it with --no-download in a temporary home, waits for engine.json, then calls
/health, /instruments and /categories with the token.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request


def main() -> int:
    exe = pathlib.Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "STEM_ENGINE_HOME": home}
        proc = subprocess.Popen([str(exe), "--no-download"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            info_path = pathlib.Path(home) / "engine.json"
            for _ in range(240):
                if info_path.exists() and info_path.stat().st_size:
                    break
                if proc.poll() is not None:
                    print(proc.stdout.read().decode(errors="replace"))
                    raise SystemExit(f"engine exited with {proc.returncode}")
                time.sleep(0.5)
            info = json.loads(info_path.read_text())
            base = f"http://127.0.0.1:{info['port']}"
            headers = {"Authorization": f"Bearer {info['token']}"}
            for _ in range(60):
                try:
                    urllib.request.urlopen(base + "/health", timeout=2)
                    break
                except OSError:
                    time.sleep(0.5)
            get = lambda p: json.load(urllib.request.urlopen(urllib.request.Request(base + p, headers=headers), timeout=10))
            inst = get("/instruments")["instruments"]
            cats = get("/categories")["categories"]
            assert len(inst) > 150 and "drums" in cats, (len(inst), list(cats))
            print(f"engine OK: {len(inst)} instruments, {len(cats)} categories, port {info['port']}")
        finally:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
