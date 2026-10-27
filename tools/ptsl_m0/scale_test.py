"""M0-a follow-up: import order, rename by track ID, and import time for a realistic batch.

Runs in the already-open test session (M0_PTSL_Test) created by m0_probe.py run-all.
Usage: python scale_test.py N_FILES SECONDS
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import time

import numpy as np
import soundfile as sf
from ptsl import PTSL_pb2 as pt, ops

import m0_probe as m

ROOT = m.ROOT


def main() -> int:
    n, seconds = int(sys.argv[1]), int(sys.argv[2])
    src = ROOT / "build" / "m0_scale_stems"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir(parents=True)
    rng = np.random.default_rng(1)
    names = [f"{chr(ord('Z') - i % 26)}{i:02d} stem" for i in range(n)]  # Z.., Y.. so not sorted
    for i, name in enumerate(names):
        ch = 2 if i % 2 else 1
        x = (rng.standard_normal((seconds * 48000, ch)) * 0.05).astype(np.float32)
        sf.write(src / f"{name}.wav", x if ch == 2 else x[:, 0], 48000, subtype="PCM_24")
    mb = sum(p.stat().st_size for p in src.iterdir()) / 1e6
    files = [src / f"{name}.wav" for name in names]

    log = m.Log()
    engine = m.connect(log)
    if engine.session_name() != m.TEST_SESSION:
        print("open the test session first (m0_probe.py run-all)")
        return 1
    before = m.track_rows(engine)
    log.step(f"import {n} files x {seconds} s ({mb:.0f} MB, ConvertAudio)",
             m.import_files, engine, files, pt.ConvertAudio)
    created = m.new_tracks(before, m.track_rows(engine))
    order = [r["name"] for r in created]
    log.step("import order follows file_list order", lambda: order == names)
    log.step("created track order", lambda: order)
    target = created[0]
    log.step(f"rename by track_id {target['id']} -> 'Renamed By ID'", m.run_op, engine,
             ops.CId_RenameTargetTrack(track_id=target["id"], new_name="Renamed By ID"))
    log.step("name after rename by id",
             lambda: [r["name"] for r in m.track_rows(engine) if r["id"] == target["id"]])
    engine.close()
    print("log:", log.save())
    return 0


if __name__ == "__main__":
    sys.exit(main())
