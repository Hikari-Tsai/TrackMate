"""Build the standalone engine that ships inside the TrackMate app (macOS and Windows).

Output: dist/stem-engine/ (one folder: the executable plus its libraries), or <dist>/stem-engine/
with --dist <dist>. The executable is built for the architecture of the Python running this
script, so the x86_64 macOS engine is built with an x86_64 Python (under Rosetta). The knowledge base
kb/mix_naming.json is bundled as stem_engine/data/mix_naming.json. Models are not bundled; the
engine downloads them on first start.

Run from engine/:  uv run --group package python packaging/build_engine.py [--dist DIR]
"""
from __future__ import annotations

import os
import pathlib
import sys

import argparse

import PyInstaller.__main__

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
ROOT = ENGINE.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=pathlib.Path, default=ENGINE / "dist")
    opts = parser.parse_args()
    work = ENGINE / "build" / "pyinstaller" / opts.dist.resolve().name
    sep = os.pathsep  # PyInstaller --add-data separator differs between platforms
    args = [
        str(HERE / "run_engine.py"),
        "--name", "stem-engine",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--distpath", str(opts.dist),
        "--workpath", str(work),
        "--specpath", str(work),
        "--collect-data", "stem_engine",
        "--add-data", f"{ROOT / 'kb' / 'mix_naming.json'}{sep}stem_engine/data",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "stem_engine",
        "--hidden-import", "stereo_analyzer",
    ]
    if sys.platform == "win32":
        args.append("--noconsole")  # started by the app; no console window
    PyInstaller.__main__.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
