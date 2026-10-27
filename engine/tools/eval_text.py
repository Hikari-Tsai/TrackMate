"""Evaluate the text layers (A/B/C) of the engine on the hand-labelled track names in
experiments/c_layer_embedding/testset_realistic.json, and sweep the C-layer thresholds.

"Auto" = the engine renames without asking (confidence high or medium). Reported:
  auto precision   correct among auto-renamed (negatives renamed count as wrong)
  auto recall      correct auto renames among all instrument names
  top-5            correct instrument among the candidates (instrument names only)
  negatives kept   non-instrument names left as they were (category other)

Usage: STEM_ENGINE_HOME=... python tools/eval_text.py [--sweep]
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

from stem_engine.config import REPO_ROOT, EngineConfig, Thresholds
from stem_engine.engine import Engine
from stem_engine.pipeline import Analyzer

TESTSET = REPO_ROOT / "experiments" / "c_layer_embedding" / "testset_realistic.json"


def evaluate(analyzer: Analyzer, items: list[dict]) -> dict:
    # Names are analysed one by one: the test set mixes unrelated sessions, so batch prefix
    # stripping would not be meaningful.
    rows = []
    for it in items:
        r = analyzer.analyze([it["name"]], audio="none", with_stereo=False)[0]
        ok_set = {it["label"], *it.get("accept", [])} if it["label"] else set()
        rows.append(dict(item=it, res=r, ok=r["instrument"] in ok_set,
                         auto=r["confidence"] in ("high", "medium"),
                         top5=bool(ok_set & {c["instrument"] for c in r["candidates"]})))
    pos = [x for x in rows if x["item"]["label"]]
    neg = [x for x in rows if not x["item"]["label"]]
    auto = [x for x in rows if x["auto"]]
    by_stage: dict[str, list] = {}
    for x in pos:
        by_stage.setdefault(x["res"]["stage"], []).append(x["ok"])
    return {
        "n_pos": len(pos), "n_neg": len(neg),
        "auto_precision": round(sum(x["ok"] for x in auto) / max(1, len(auto)), 3),
        "auto_recall": round(sum(x["ok"] and x["auto"] for x in pos) / len(pos), 3),
        "top1": round(sum(x["ok"] for x in pos) / len(pos), 3),
        "top5": round(sum(x["top5"] for x in pos) / len(pos), 3),
        "negatives_kept": round(sum(x["res"]["category"] == "other" for x in neg) / max(1, len(neg)), 3),
        "negatives_auto_renamed": sum(x["auto"] for x in neg),
        "by_stage": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_stage.items())},
        "errors": [(x["item"]["name"], x["item"]["label"], x["res"]["instrument"], x["res"]["stage"],
                    x["res"]["confidence"]) for x in rows if not x["ok"] and (x["auto"] or x["item"]["label"])],
    }


def main() -> int:
    items = json.loads(TESTSET.read_text())["items"]
    engine = Engine(EngineConfig())
    base = engine.analyzer()
    if "--sweep" in sys.argv:
        print("c_high c_low margin | auto_prec auto_rec top1 top5 neg_kept neg_auto")
        for c_high in (0.74, 0.77, 0.80, 0.83, 0.86):
            for c_low in (0.55, 0.62, 0.68):
                for margin in (0.0, 0.03):
                    th = dataclasses.replace(Thresholds(), c_high=c_high, c_low=c_low, c_high_margin=margin)
                    r = evaluate(Analyzer(base.kb, base.index, None, th), items)
                    print(f"{c_high:.2f}  {c_low:.2f}  {margin:.2f}  | {r['auto_precision']:.3f} {r['auto_recall']:.3f} "
                          f"{r['top1']:.3f} {r['top5']:.3f} {r['negatives_kept']:.3f} {r['negatives_auto_renamed']}")
        return 0
    r = evaluate(Analyzer(base.kb, base.index, None, base.th), items)
    errors = r.pop("errors")
    print(json.dumps(r, indent=1))
    print("errors (name, label, predicted, stage, confidence):")
    for e in errors:
        print("  ", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
