"""Evaluate layer D as the engine runs it (ONNX 8-bit, loudest segments, class prototypes) on
Medley-solos-DB test clips, a fixed number per class. Reports category accuracy, accuracy among
confident answers (prob >= d_min_prob) and the probability distribution.

Usage: STEM_ENGINE_HOME=... python tools/eval_audio.py [PER_CLASS]
"""
from __future__ import annotations

import csv
import sys
import time
from collections import Counter

import numpy as np

from stem_engine.config import REPO_ROOT, EngineConfig
from stem_engine.engine import Engine

MEDLEY = REPO_ROOT / "experiments" / "datasets" / "medley_solos"
TO_CATEGORY = {"clarinet": "woodwinds", "flute": "woodwinds", "tenor saxophone": "woodwinds",
               "distorted electric guitar": "guitars", "female singer": "lead_vocals", "piano": "keys",
               "trumpet": "brass", "violin": "strings"}


def main() -> int:
    per_class = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    engine = Engine(EngineConfig())
    clf = engine.analyzer().audio
    meta = next(MEDLEY.glob("*.csv"))
    rows = [r for r in csv.DictReader(open(meta)) if r["subset"] == "test"]
    rng = np.random.default_rng(0)
    picked = []
    for name in TO_CATEGORY:
        cls = [r for r in rows if r["instrument"] == name]
        picked += [cls[i] for i in rng.choice(len(cls), per_class, replace=False)]
    results, t0 = [], time.perf_counter()
    for r in picked:
        path = next((MEDLEY / "audio").glob(f"Medley-solos-DB_test-{r['instrument_id']}_{r['uuid4']}.wav"))
        d = clf.classify(str(path))
        truth = TO_CATEGORY[r["instrument"]]
        ok = d.best_category == truth or (truth == "lead_vocals" and d.best_category == "backing_vocals")
        results.append((r["instrument"], truth, d.best_category, d.best_prob, ok))
    secs = (time.perf_counter() - t0) / len(results)
    th = engine.config.thresholds.d_min_prob
    conf = [x for x in results if x[3] >= th]
    print(f"clips={len(results)}  {secs:.2f} s/clip  accuracy={np.mean([x[4] for x in results]):.3f}  "
          f"confident(p>={th})={len(conf)}  accuracy_confident={np.mean([x[4] for x in conf]):.3f}")
    print("prob quantiles 10/50/90:", np.round(np.quantile([x[3] for x in results], [0.1, 0.5, 0.9]), 3))
    print("threshold  answered  accuracy_of_answered")
    for t in (0.15, 0.18, 0.20, 0.22, 0.25, 0.30, 0.35):
        sel = [x for x in results if x[3] >= t]
        print(f"  {t:.2f}     {len(sel) / len(results):.3f}     {np.mean([x[4] for x in sel]) if sel else float('nan'):.3f}")
    print("errors:", [(x[0], x[2], round(x[3], 3)) for x in results if not x[4]])
    for name in TO_CATEGORY:
        sel = [x for x in results if x[0] == name]
        print(f"  {name:26s} acc={np.mean([x[4] for x in sel]):.2f}  predicted={Counter(x[2] for x in sel).most_common(3)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
