"""End-to-end check against a running engine and an open Pro Tools session:
POST /analyze -> build the /apply payload the front end would send -> dry run -> apply ->
GET /session. Writes the responses next to the stems folder.

The payload uses the Top-1 name and category, and converts to mono whenever the stereo
analysis recommends it. Use a test session: this adds folders and tracks to whatever is open.

Usage: python tools/e2e_apply.py STEMS_DIR [ENGINE_HOME]
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    stems = pathlib.Path(sys.argv[1]).resolve()
    home = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else
                        pathlib.Path.home() / "Library" / "Application Support" / "StemEngine")
    info = json.loads((home / "engine.json").read_text())
    base = f"http://127.0.0.1:{info['port']}"
    headers = {"Authorization": f"Bearer {info['token']}", "Content-Type": "application/json"}

    def call(method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        t = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return r.status, json.load(r), time.perf_counter() - t
        except urllib.error.HTTPError as e:
            return e.code, json.load(e), time.perf_counter() - t

    files = sorted(str(p) for p in stems.glob("*.wav"))
    status, body, secs = call("POST", "/analyze", {"files": files, "audio": "auto"})
    print(f"/analyze {status} {secs:.1f}s")
    tracks = body["tracks"]
    for t in tracks:
        print(f"  {t['original_name']:22s} -> {t['proposed_name']:16s} {t['category']:14s} "
              f"{t['confidence']:6s} {t['stage']:4s} stereo={t['stereo']['type']}/{t['stereo']['action']}")
    payload = {"tracks": [{"file": t["file"], "name": t["proposed_name"], "category": t["category"],
                           "mono": t["stereo"].get("action", "keep") != "keep"} for t in tracks]}

    status, body, secs = call("POST", "/apply", {**payload, "dry_run": True})
    print(f"\n/apply dry run {status} {secs:.1f}s")
    for f in body["plan"]:
        names = ", ".join(x["final_name"] + (" (mono)" if x["mono"] else "") for x in f["tracks"])
        print(f"  {f['folder']:8s} exists={f['exists']!s:5s} colour={f['color_index']:2d}  {names}")

    status, result, secs = call("POST", "/apply", payload)
    print(f"\n/apply {status} {secs:.1f}s ok={result.get('ok')}")
    for r in result.get("results", []):
        print(f"  {pathlib.Path(r['file']).name:24s} -> {r['pt_name']!s:16s} folder={r['folder']:8s} "
              f"name={r['name_ok']} folder={r['folder_ok']} colour={r['color_ok']} errors={r['errors']}")

    status, session, _ = call("GET", "/session")
    print("\nsession:")
    for t in session["tracks"]:
        print(f"  {t['index']:2d} {t['name']:16s} {t['type']:12s} {t['format']:10s} "
              f"folder={t['folder']!s:8s} colour={t['color']}")
    out = stems.parent / f"{stems.name}_e2e.json"
    out.write_text(json.dumps({"analyze": tracks, "apply": result, "session": session}, ensure_ascii=False, indent=1))
    print("saved", out)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
