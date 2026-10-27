"""Compare the exported PE-AV audio ONNX graph with PyTorch on real audio of several lengths.

Clips: Medley-solos-DB test (about 3 s) and NSynth test (4 s), plus 10 s and 30 s windows made by
concatenating Medley clips. Every input goes through PeAudioFeatureExtractor exactly as in
the evaluation (reflect padding to a multiple of 1920 samples, mask all ones) and is fed
one clip at a time to both models.

Reports cosine similarity, relative L2 error, and whether the top-1 class against the
Medley prototypes agrees.

Usage: python verify_peav_parity.py ONNX_FILE [--per-length N]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import onnxruntime as ort
import torch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "instrument_zeroshot"))
from eval_instruments import PEAV, class_prototypes, load_dataset, read_mono  # noqa: E402


def clips(per_length: int) -> list[tuple[str, np.ndarray]]:
    rng = np.random.default_rng(0)
    medley = load_dataset("medley_solos")
    nsynth = load_dataset("nsynth")
    pick = lambda items, n: [items[i] for i in rng.choice(len(items), n, replace=False)]
    out = [("medley~3s", read_mono(it["path"], 48000)) for it in pick(medley, per_length)]
    out += [("nsynth 4s", read_mono(it["path"], 48000)) for it in pick(nsynth, per_length)]
    for seconds in (10, 30):
        for _ in range(max(2, per_length // 4)):
            wave = np.concatenate([read_mono(it["path"], 48000) for it in pick(medley, seconds // 2)])
            out.append((f"concat {seconds}s", wave[:48000 * seconds]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("onnx_file")
    ap.add_argument("--per-length", type=int, default=40)
    args = ap.parse_args()
    ref = PEAV()  # PyTorch reference, same loading path as the evaluation
    classes, protos = class_prototypes(ref, "medley_solos")
    sess = ort.InferenceSession(args.onnx_file, providers=["CPUExecutionProvider"])
    rows = []
    for tag, wave in clips(args.per_length):
        batch = ref.fe([wave], sampling_rate=48000, return_tensors="pt")
        assert int(batch["padding_mask"].sum()) == batch["padding_mask"].numel(), "single clip should be unmasked"
        with torch.no_grad():
            a = ref.model.get_audio_embeds(batch["input_values"].to(ref.dev),
                                           batch["padding_mask"].to(ref.dev)).float().cpu().numpy()[0]
        b = sess.run(["audio_embedding"], {"input_values": batch["input_values"].numpy()})[0][0]
        cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
        rel = float(np.linalg.norm(a - b) / np.linalg.norm(a))
        same = int(np.argmax(protos @ a) == np.argmax(protos @ b))
        rows.append((tag, cos, rel, same))
    for tag in dict.fromkeys(r[0] for r in rows):
        sel = [r for r in rows if r[0] == tag]
        print(f"{tag:12s} n={len(sel):3d}  min_cos={min(r[1] for r in sel):.6f}  mean_cos={np.mean([r[1] for r in sel]):.6f}"
              f"  max_rel_err={max(r[2] for r in sel):.5f}  top1_agree={np.mean([r[3] for r in sel]) * 100:.1f}%")
    worst = min(r[1] for r in rows)
    print(f"ALL n={len(rows)} min_cos={worst:.6f} -> {'PASS' if worst > 0.999 else 'FAIL'} (threshold 0.999)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
