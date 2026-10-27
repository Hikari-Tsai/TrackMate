"""Compare an exported Qwen3-Embedding ONNX model with the official sentence-transformers output.

Texts: every alias in kb/mix_naming.json plus the hand-labelled track names, each with the
symmetric instruction used by the C layer, encoded in mixed-length batches so left padding
and dynamic shapes are exercised.

Usage: python verify_parity.py MODEL_DIR ONNX_FILE [--reference cache.npy]
Prints min / mean cosine and writes the per-text cosines next to the ONNX file.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "c_layer_embedding"))
from run_compare import QWEN_TASK_SYM, load_entries, normalize  # noqa: E402

PROMPT = f"Instruct: {QWEN_TASK_SYM}\nQuery:"


def texts() -> list[str]:
    kb = json.loads((ROOT / "kb" / "mix_naming.json").read_text())
    names = [e["text"] for e in load_entries(kb)]
    real = json.loads((ROOT / "experiments" / "c_layer_embedding" / "testset_realistic.json").read_text())["items"]
    names += [normalize(it["name"]) or it["name"] for it in real]
    return [PROMPT + n for n in names]


def onnx_embed(model_dir: pathlib.Path, onnx_file: pathlib.Path, items: list[str], batch: int = 32) -> np.ndarray:
    tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    pad_id = tok.token_to_id("<|endoftext|>")
    sess = ort.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(items), batch):
        enc = [tok.encode(t).ids for t in items[i:i + batch]]
        width = max(map(len, enc))
        ids = np.array([[pad_id] * (width - len(e)) + e for e in enc], dtype=np.int64)  # left padding
        mask = np.array([[0] * (width - len(e)) + [1] * len(e) for e in enc], dtype=np.int64)
        out.append(sess.run(["sentence_embedding"], {"input_ids": ids, "attention_mask": mask})[0])
    return np.concatenate(out)


def reference_embed(items: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device="cpu")
    return model.encode(items, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("onnx_file")
    ap.add_argument("--reference", help="cache file for the PyTorch reference embeddings")
    args = ap.parse_args()
    items = texts()
    ref_path = pathlib.Path(args.reference) if args.reference else None
    if ref_path and ref_path.exists():
        ref = np.load(ref_path)
    else:
        ref = reference_embed(items)
        if ref_path:
            np.save(ref_path, ref)
    got = onnx_embed(pathlib.Path(args.model_dir), pathlib.Path(args.onnx_file), items)
    cos = np.sum(ref * got, axis=1) / (np.linalg.norm(ref, axis=1) * np.linalg.norm(got, axis=1))
    worst = np.argsort(cos)[:5]
    print(f"texts={len(items)} min_cos={cos.min():.6f} mean_cos={cos.mean():.6f} "
          f"p01={np.percentile(cos, 1):.6f}")
    for i in worst:
        print(f"  {cos[i]:.6f}  {items[i][len(PROMPT):]!r}")
    np.save(pathlib.Path(args.onnx_file).with_suffix(".parity.npy"), cos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
