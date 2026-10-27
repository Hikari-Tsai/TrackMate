"""Build the standalone engine that ships inside the TrackMate app (macOS and Windows).

Output: dist/stem-engine/ (one folder: the executable plus its libraries). The knowledge base
kb/mix_naming.json is bundled as stem_engine/data/mix_naming.json. Models are not bundled; the
engine downloads them on first start.

Run from engine/:  uv run --group package python packaging/build_engine.py
"""
from __future__ import annotations

import os
import pathlib
import sys

import PyInstaller.__main__

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
ROOT = ENGINE.parent


def main() -> int:
    sep = os.pathsep  # PyInstaller --add-data separator differs between platforms
    args = [
        str(HERE / "run_engine.py"),
        "--name", "stem-engine",
        "--onedir",
        "--noconfirm",
        "--clean",
        "--distpath", str(ENGINE / "dist"),
        "--workpath", str(ENGINE / "build" / "pyinstaller"),
        "--specpath", str(ENGINE / "build" / "pyinstaller"),
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
