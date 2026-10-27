"""C-layer experiment: track name -> instrument id with text embeddings.

Compares multilingual-e5-small, Qwen3-Embedding-0.6B (with and without an
instruction) and a rapidfuzz baseline on three tests built from
kb/mix_naming.json:

  loo        leave-one-out: query an English alias/abbreviation after removing
             that exact string from the index (can the model generalise from the
             instrument's other aliases?)
  crossling  zh / ja aliases against an English-only index
  realistic  hand-labelled noisy track names (testset_realistic.json) against the
             full index, including non-instrument names that must be rejected

Usage: python run_compare.py [--models e5,qwen,qwen_noinst,fuzzy]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import time
import unicodedata

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
KB_PATH = HERE.parent.parent / "kb" / "mix_naming.json"
OUT = HERE / "results"

QWEN_TASK = ("Given the name of a track or audio file from a music production session, "
             "retrieve the standard instrument name it refers to")
QWEN_TASK_SYM = ("Given a track name from a music production session, "
                 "retrieve names that refer to the same instrument")

_SEP = re.compile(r"[_\-.,+()\[\]{}【】「」/\\|:;#*＊~]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKC", name)
    s = re.sub(r"\.(wav|aiff?|mp3|flac|m4a|ogg)$", "", s, flags=re.I)
    s = re.sub(r"\.dup\d+$", "", s, flags=re.I)
    s = re.sub(r"\d{2,3}\s?bpm", " ", s, flags=re.I)
    s = _CAMEL.sub(" ", s)
    s = _SEP.sub(" ", s).lower()
    tokens = [t for t in s.split() if not t.isdigit()]  # instance numbers / dates
    return " ".join(tokens)


# --------------------------------------------------------------------- index
def load_entries(kb: dict) -> list[dict]:
    rows = []
    for cat in kb["categories"]:
        for inst in cat["instruments"]:
            def add(text, kind, lang):
                t = normalize(text)
                if t:
                    rows.append(dict(text=t, inst=inst["id"], cat=cat["id"], kind=kind, lang=lang))
            add(inst["canonical"], "canonical", "en")
            for a in inst.get("aliases", []):
                add(a, "alias", "en")
            for a in inst.get("abbreviations", []):
                add(a, "abbrev", "en")
            for a in inst.get("zh", []):
                add(a, "zh", "zh")
            for a in inst.get("ja", []):
                add(a, "ja", "ja")
    # de-duplicate identical (text, inst) pairs
    seen, out = set(), []
    for r in rows:
        if (r["text"], r["inst"]) not in seen:
            seen.add((r["text"], r["inst"]))
            out.append(r)
    return out


def inst_category(kb: dict) -> dict[str, str]:
    return {i["id"]: c["id"] for c in kb["categories"] for i in c["instruments"]}


# ------------------------------------------------------------------ scorers
class EmbeddingScorer:
    def __init__(self, name: str, model_id: str, query_prompt: str = "", doc_prompt: str = ""):
        import torch
        from sentence_transformers import SentenceTransformer
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        t0 = time.perf_counter()
        self.model = SentenceTransformer(model_id, device=device)
        self.load_seconds = time.perf_counter() - t0
        self.name, self.model_id = name, model_id
        self.query_prompt, self.doc_prompt = query_prompt, doc_prompt
        self.params = sum(p.numel() for p in self.model.parameters())
        self.device = device

    def encode(self, texts: list[str], query: bool) -> np.ndarray:
        prompt = self.query_prompt if query else self.doc_prompt
        return self.model.encode(texts, prompt=prompt or None, batch_size=64,
                                 normalize_embeddings=True, convert_to_numpy=True)

    def similarity(self, queries: list[str], docs: list[str]) -> np.ndarray:
        return self.encode(queries, True) @ self.encode(docs, False).T

    def latency_ms(self, sample: list[str], repeats: int = 30) -> float:
        self.encode(sample[:1], True)  # warm-up
        t0 = time.perf_counter()
        for i in range(repeats):
            self.encode([sample[i % len(sample)]], True)
        return (time.perf_counter() - t0) / repeats * 1000


class OnnxQwenScorer:
    """Our exported Qwen3-Embedding ONNX (pooling + normalisation inside the graph), run the
    way the app will: tokenizers + onnxruntime on CPU, left padding, symmetric instruction."""
    ONNX_DIR = HERE.parent.parent / "build" / "hf" / "Qwen3-Embedding-0.6B-ONNX"

    def __init__(self, name: str, onnx_file: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        t0 = time.perf_counter()
        self.tok = Tokenizer.from_file(str(self.ONNX_DIR / "tokenizer.json"))
        self.pad_id = self.tok.token_to_id("<|endoftext|>")
        self.sess = ort.InferenceSession(str(self.ONNX_DIR / "onnx" / onnx_file), providers=["CPUExecutionProvider"])
        self.load_seconds = time.perf_counter() - t0
        self.name, self.model_id, self.params, self.device = name, f"onnx/{onnx_file}", 595776512, "cpu"
        self.prompt = f"Instruct: {QWEN_TASK_SYM}\nQuery:"

    def encode(self, texts: list[str], query: bool = True, batch: int = 32) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch):
            enc = [self.tok.encode(self.prompt + t).ids for t in texts[i:i + batch]]
            width = max(map(len, enc))
            ids = np.array([[self.pad_id] * (width - len(e)) + e for e in enc], dtype=np.int64)
            mask = np.array([[0] * (width - len(e)) + [1] * len(e) for e in enc], dtype=np.int64)
            out.append(self.sess.run(["sentence_embedding"], {"input_ids": ids, "attention_mask": mask})[0])
        return np.concatenate(out)

    def similarity(self, queries: list[str], docs: list[str]) -> np.ndarray:
        return self.encode(queries) @ self.encode(docs).T

    def latency_ms(self, sample: list[str], repeats: int = 30) -> float:
        self.encode(sample[:1])
        t0 = time.perf_counter()
        for i in range(repeats):
            self.encode([sample[i % len(sample)]])
        return (time.perf_counter() - t0) / repeats * 1000


class FuzzyScorer:
    name, model_id, params, device, load_seconds = "fuzzy", "rapidfuzz WRatio", 0, "cpu", 0.0

    def similarity(self, queries: list[str], docs: list[str]) -> np.ndarray:
        from rapidfuzz import fuzz, process
        return process.cdist(queries, docs, scorer=fuzz.WRatio, workers=-1).astype(np.float32) / 100.0

    def latency_ms(self, sample: list[str], repeats: int = 30) -> float:
        return float("nan")


def make_scorer(key: str):
    if key == "e5":
        return EmbeddingScorer("e5-small", "intfloat/multilingual-e5-small", "query: ", "query: ")
    if key == "qwen":
        return EmbeddingScorer("qwen3-0.6b", "Qwen/Qwen3-Embedding-0.6B", f"Instruct: {QWEN_TASK}\nQuery:")
    if key == "qwen_sym":  # symmetric task: same instruction on both sides, like e5's "query: " prefix
        prompt = f"Instruct: {QWEN_TASK_SYM}\nQuery:"
        return EmbeddingScorer("qwen3-0.6b-sym", "Qwen/Qwen3-Embedding-0.6B", prompt, prompt)
    if key == "qwen_noinst":
        return EmbeddingScorer("qwen3-0.6b-noinst", "Qwen/Qwen3-Embedding-0.6B")
    if key == "qwen_onnx_fp32":
        return OnnxQwenScorer("qwen3-onnx-fp32", "model.onnx")
    if key == "qwen_onnx_int8":
        return OnnxQwenScorer("qwen3-onnx-int8", "model_int8.onnx")
    if key == "qwen_onnx_block8":
        return OnnxQwenScorer("qwen3-onnx-block8", "model_block8.onnx")
    if key == "qwen_onnx_block8acc4":
        return OnnxQwenScorer("qwen3-onnx-block8acc4", "model_block8acc4.onnx")
    if key == "bge":  # dense output only; BGE-M3 needs no prefix for queries or documents
        return EmbeddingScorer("bge-m3", "BAAI/bge-m3")
    if key == "fuzzy":
        return FuzzyScorer()
    raise ValueError(key)


# --------------------------------------------------------------- retrieval
def rank_instruments(sim: np.ndarray, entries: list[dict], mask: np.ndarray | None = None):
    """Per query: best instrument (max over its entries), its score and the best other instrument."""
    if mask is not None:
        sim = np.where(mask, -np.inf, sim)
    insts = sorted({e["inst"] for e in entries})
    col = {i: k for k, i in enumerate(insts)}
    per_inst = np.full((sim.shape[0], len(insts)), -np.inf, dtype=np.float32)
    for j, e in enumerate(entries):
        k = col[e["inst"]]
        per_inst[:, k] = np.maximum(per_inst[:, k], sim[:, j])
    order = np.argsort(-per_inst, axis=1)
    results = []
    for q in range(sim.shape[0]):
        a, b = order[q, 0], order[q, 1]
        results.append(dict(pred=insts[a], s1=float(per_inst[q, a]), pred2=insts[b], s2=float(per_inst[q, b]),
                            top5=[insts[k] for k in order[q, :5]]))
    return results


def accuracy(rows: list[dict], cat_of: dict[str, str]) -> dict:
    """Top-1 exact/category accuracy plus Recall@3 / Recall@5: the correct instrument is
    among the k highest-ranked distinct instruments (every query gets a ranked answer)."""
    n = len(rows)
    if not n:
        return dict(n=0)
    exact = sum(r["pred"] in r["targets"] for r in rows)
    cat = sum(cat_of[r["pred"]] in {cat_of[t] for t in r["targets"]} for r in rows)
    at = lambda k: round(sum(bool(r["targets"] & set(r["top5"][:k])) for r in rows) / n, 4)
    return dict(n=n, exact=round(exact / n, 4), category=round(cat / n, 4), recall_at_3=at(3), recall_at_5=at(5))


def coverage_at_precision(rows: list[dict], key: str, targets: tuple[float, ...] = (0.95, 0.98)) -> dict:
    """Accept items with score >= t. Negatives (no targets) accepted count as errors."""
    positives = sum(bool(r["targets"]) for r in rows)
    scored = sorted(rows, key=lambda r: -r[key])
    best = {p: dict(coverage=0.0, threshold=None) for p in targets}
    correct = accepted = 0
    for i, r in enumerate(scored):
        accepted += 1
        correct += bool(r["targets"]) and r["pred"] in r["targets"]
        if i + 1 < len(scored) and scored[i + 1][key] == r[key]:
            continue  # evaluate only at distinct thresholds
        precision = correct / accepted
        for p in targets:
            if precision >= p and correct / positives > best[p]["coverage"]:
                best[p] = dict(coverage=round(correct / positives, 4), threshold=round(r[key], 4))
    return best


# --------------------------------------------------------------- dictionary A-layer (for subsets)
def a_layer_predict(name: str, en_terms: dict[str, set[str]], cjk_terms: dict[str, set[str]]) -> str | None:
    """Longest exact phrase (English, whole tokens) or longest CJK substring; None if absent or ambiguous."""
    tokens = name.split()
    for n in range(min(4, len(tokens)), 0, -1):
        hits = set()
        for i in range(len(tokens) - n + 1):
            hits |= en_terms.get(" ".join(tokens[i:i + n]), set())
        if hits:
            return next(iter(hits)) if len(hits) == 1 else None
    for term in sorted((t for t in cjk_terms if len(t) >= 2 and t in name), key=len, reverse=True):
        owners = cjk_terms[term]
        return next(iter(owners)) if len(owners) == 1 else None
    return None


# --------------------------------------------------------------- tests
def run(scorer, kb, entries, cat_of, realistic) -> dict:
    # entries are unique per (text, inst), so a text with several owners is ambiguous
    ambiguous = {t for t, owners in collections.Counter(e["text"] for e in entries).items() if owners > 1}
    en = [e for e in entries if e["lang"] == "en"]
    en_texts = [e["text"] for e in en]
    en_text_arr, en_inst_arr = np.array(en_texts), np.array([e["inst"] for e in en])
    report = dict(model=scorer.name, model_id=scorer.model_id, params=scorer.params, device=scorer.device)

    # 1) leave-one-out over English aliases / abbreviations
    loo_q = [e for e in en if e["kind"] in ("alias", "abbrev") and e["text"] not in ambiguous]
    uniq = {}
    for e in loo_q:
        uniq.setdefault(e["text"], e)
    loo_q = list(uniq.values())
    sim = scorer.similarity([e["text"] for e in loo_q], en_texts)
    mask = en_text_arr[None, :] == np.array([q["text"] for q in loo_q])[:, None]
    same_inst = en_inst_arr[None, :] == np.array([q["inst"] for q in loo_q])[:, None]
    reachable = (same_inst & ~mask).any(axis=1)  # instrument still has another entry in the index
    ranked = rank_instruments(sim, en, mask)
    loo_rows = [dict(query=q["text"], kind=q["kind"], targets={q["inst"]}, **r)
                for q, r, ok in zip(loo_q, ranked, reachable) if ok]
    report["loo_alias"] = accuracy([r for r in loo_rows if r["kind"] == "alias"], cat_of)
    report["loo_abbrev"] = accuracy([r for r in loo_rows if r["kind"] == "abbrev"], cat_of)

    # 2) cross-lingual: zh / ja aliases against the English-only index
    cl_q = {}
    for e in entries:
        if e["lang"] in ("zh", "ja") and e["text"] not in ambiguous:
            cl_q.setdefault((e["lang"], e["text"]), e)
    cl_q = list(cl_q.values())
    ranked = rank_instruments(scorer.similarity([e["text"] for e in cl_q], en_texts), en)
    cl_rows = [dict(query=q["text"], lang=q["lang"], targets={q["inst"]}, **r) for q, r in zip(cl_q, ranked)]
    report["crossling_zh"] = accuracy([r for r in cl_rows if r["lang"] == "zh"], cat_of)
    report["crossling_ja"] = accuracy([r for r in cl_rows if r["lang"] == "ja"], cat_of)

    # 2b) CJK leave-one-out against the full index: an unseen zh/ja variant while the
    #     index still holds the instrument's other zh/ja/en aliases (deployment setting)
    all_text_arr = np.array([e["text"] for e in entries])
    all_inst_arr = np.array([e["inst"] for e in entries])
    mask = all_text_arr[None, :] == np.array([q["text"] for q in cl_q])[:, None]
    same_inst = all_inst_arr[None, :] == np.array([q["inst"] for q in cl_q])[:, None]
    reachable = (same_inst & ~mask).any(axis=1)
    ranked = rank_instruments(scorer.similarity([e["text"] for e in cl_q], list(all_text_arr)), entries, mask)
    cjk_rows = [dict(query=q["text"], lang=q["lang"], targets={q["inst"]}, **r)
                for q, r, ok in zip(cl_q, ranked, reachable) if ok]
    report["loo_zh_full_index"] = accuracy([r for r in cjk_rows if r["lang"] == "zh"], cat_of)
    report["loo_ja_full_index"] = accuracy([r for r in cjk_rows if r["lang"] == "ja"], cat_of)

    # 3) realistic names against the full (deployment) index
    all_texts = [e["text"] for e in entries]
    en_terms, cjk_terms = collections.defaultdict(set), collections.defaultdict(set)
    for e in entries:
        (en_terms if e["lang"] == "en" else cjk_terms)[e["text"]].add(e["inst"])
    names = [normalize(it["name"]) or it["name"] for it in realistic]
    ranked = rank_instruments(scorer.similarity(names, all_texts), entries)
    real_rows = []
    for it, q, r in zip(realistic, names, ranked):
        targets = set() if it["label"] is None else {it["label"], *it.get("accept", [])}
        real_rows.append(dict(name=it["name"], query=q, group=it["group"], targets=targets,
                              a_pred=a_layer_predict(q, en_terms, cjk_terms), margin=r["s1"] - r["s2"], **r))
    pos = [r for r in real_rows if r["targets"]]
    neg = [r for r in real_rows if not r["targets"]]
    # What the C layer actually receives: names the dictionary missed or got wrong,
    # plus non-instrument names the dictionary (correctly) did not claim.
    residual = [r for r in pos if r["a_pred"] not in r["targets"]]
    residual_neg = [r for r in neg if r["a_pred"] is None]
    a_claimed = [r for r in pos if r["a_pred"] is not None]
    report["a_layer"] = dict(
        coverage=round(len(a_claimed) / len(pos), 4),
        precision=round(sum(r["a_pred"] in r["targets"] for r in a_claimed) / len(a_claimed), 4),
        negatives_claimed=sum(r["a_pred"] is not None for r in neg))
    report["realistic_all"] = accuracy(pos, cat_of)
    report["realistic_residual"] = accuracy(residual, cat_of)
    report["realistic_by_group"] = {g: accuracy([r for r in pos if r["group"] == g], cat_of)
                                    for g in sorted({r["group"] for r in pos})}
    report["residual_by_group"] = dict(collections.Counter(r["group"] for r in residual))
    report["negatives_s1"] = dict(mean=round(float(np.mean([r["s1"] for r in neg])), 4),
                                  max=round(float(np.max([r["s1"] for r in neg])), 4))
    report["positives_correct_s1_median"] = round(float(np.median(
        [r["s1"] for r in pos if r["pred"] in r["targets"]])), 4)
    report["threshold_s1_residual"] = coverage_at_precision(residual + residual_neg, "s1")
    report["threshold_margin_residual"] = coverage_at_precision(residual + residual_neg, "margin")
    report["latency_ms_per_query"] = round(scorer.latency_ms(names), 2)
    report["load_seconds"] = round(scorer.load_seconds, 1)

    def dump(rows):
        return [{k: (sorted(v) if isinstance(v, set) else v) for k, v in r.items()} for r in rows]
    details = dict(loo=dump(loo_rows), crossling=dump(cl_rows), loo_cjk=dump(cjk_rows), realistic=dump(real_rows))
    return report, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="fuzzy,e5,qwen,qwen_noinst")
    args = ap.parse_args()
    kb = json.loads(KB_PATH.read_text())
    entries = load_entries(kb)
    cat_of = inst_category(kb)
    realistic = json.loads((HERE / "testset_realistic.json").read_text())["items"]
    OUT.mkdir(exist_ok=True)
    summary_path = OUT / "summary.json"
    # keep results of models not re-run this time
    summary = json.loads(summary_path.read_text())["runs"] if summary_path.exists() else []
    rerun = set(args.models.split(","))
    summary = [r for r in summary if r.get("key") not in rerun]
    for key in args.models.split(","):
        scorer = make_scorer(key)
        t0 = time.perf_counter()
        report, details = run(scorer, kb, entries, cat_of, realistic)
        report["total_seconds"] = round(time.perf_counter() - t0, 1)
        report["key"] = key
        summary.append(report)
        (OUT / f"details_{scorer.name}.json").write_text(json.dumps(details, ensure_ascii=False, indent=1))
        print(json.dumps(report, ensure_ascii=False))
        del scorer
    summary_path.write_text(json.dumps(dict(index_entries=len(entries), runs=summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
