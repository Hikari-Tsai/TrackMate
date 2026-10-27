"""Layer C (README: Recognition pipeline): Qwen3-Embedding ONNX over every KB spelling plus NONE anchors.

Both the query and the index carry the same instruction (the symmetric form scored best in
experiments/c_layer_embedding). Index vectors are cached on disk per model file, keyed by text,
so a new user alias costs one encode call instead of a rebuild.
"""
from __future__ import annotations

import hashlib
import pathlib
import threading
from dataclasses import dataclass

import numpy as np

from .kb import KnowledgeBase, norm

TASK = "Given a track name from a music production session, retrieve names that refer to the same instrument"
PAD_TOKEN = "<|endoftext|>"
# Words that name a take, a session or a placeholder rather than an instrument. Scores close
# to these mean "not an instrument" (non-instrument names scored 0.87 on average without them).
NONE_ANCHORS = ["audio", "audio track", "track", "new track", "untitled", "take", "comp", "session", "idea",
                "demo", "test", "temp", "version", "edit", "song", "final", "copy", "alt", "region", "clip",
                "consolidated", "export", "render", "record", "rec", "voice memo", "my song",
                "音軌", "軌道", "未命名", "錄音", "トラック", "オーディオ", "テイク", "新規トラック", "録音"]


class TextEmbedder:
    def __init__(self, model_dir: pathlib.Path, onnx_file: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.pad_id = self.tok.token_to_id(PAD_TOKEN)
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(model_dir / onnx_file), opts, providers=["CPUExecutionProvider"])
        self.prefix = f"Instruct: {TASK}\nQuery:"
        self.model_key = hashlib.sha256(f"{model_dir.name}/{onnx_file}/{TASK}".encode()).hexdigest()[:16]

    def encode(self, texts: list[str], batch: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1024), np.float32)
        out = []
        for i in range(0, len(texts), batch):
            enc = [self.tok.encode(self.prefix + t).ids for t in texts[i:i + batch]]
            width = max(map(len, enc))
            ids = np.array([[self.pad_id] * (width - len(e)) + e for e in enc], dtype=np.int64)
            mask = np.array([[0] * (width - len(e)) + [1] * len(e) for e in enc], dtype=np.int64)
            out.append(self.sess.run(["sentence_embedding"], {"input_ids": ids, "attention_mask": mask})[0])
        return np.concatenate(out).astype(np.float32)


@dataclass
class CResult:
    top: list[tuple[str, float]]   # up to 5 (instrument, cosine), best first
    s1: float
    margin: float                  # s1 - best other instrument
    none_score: float              # best NONE anchor

    @property
    def none_margin(self) -> float:
        return self.s1 - self.none_score


class EmbeddingIndex:
    """Cosine search over KB spellings (+ user aliases) with NONE anchors."""

    def __init__(self, kb: KnowledgeBase, embedder, cache_dir: pathlib.Path | None = None):
        self.kb = kb
        self.embedder = embedder
        self.cache_path = (cache_dir / f"c_index_{embedder.model_key}.npz") if cache_dir else None
        self._lock = threading.Lock()
        self._vectors: dict[str, np.ndarray] = {}
        self._load_cache()
        self.rebuild()

    def _load_cache(self) -> None:
        if self.cache_path and self.cache_path.exists():
            data = np.load(self.cache_path, allow_pickle=False)
            self._vectors = dict(zip(data["texts"].tolist(), data["vectors"]))

    def _save_cache(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        texts = list(self._vectors)
        tmp = self.cache_path.with_name(self.cache_path.stem + ".tmp.npz")
        np.savez(tmp, texts=np.array(texts), vectors=np.stack([self._vectors[t] for t in texts]))
        tmp.replace(self.cache_path)

    def _vectors_for(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self._vectors]
        if missing:
            for t, v in zip(missing, self.embedder.encode(missing)):
                self._vectors[t] = v
            self._save_cache()
        return np.stack([self._vectors[t] for t in texts])

    def rebuild(self) -> None:
        """(Re)build the matrix; call after user aliases change."""
        with self._lock:
            rows = [(e.text, e.inst) for e in self.kb.entries]
            rows += [(text, inst) for text, inst in self.kb.user_aliases.items()]
            anchors = [norm(a) for a in NONE_ANCHORS if norm(a) not in self.kb.phrases]
            self.texts = [t for t, _ in rows]
            self.owner = [i for _, i in rows]
            self.matrix = self._vectors_for(self.texts)
            self.none_matrix = self._vectors_for(anchors)
            insts = sorted(set(self.owner))
            self.inst_names = insts
            col = {i: k for k, i in enumerate(insts)}
            cols = np.array([col[i] for i in self.owner])
            # Rows grouped by instrument so a per-instrument max is one reduceat call.
            self.row_order = np.argsort(cols, kind="stable")
            self.group_starts = np.searchsorted(cols[self.row_order], np.arange(len(insts)))

    def query(self, texts: list[str], k: int = 5) -> list[CResult]:
        if not texts:
            return []
        q = self.embedder.encode(texts)
        with self._lock:
            sim = q @ self.matrix.T
            none = (q @ self.none_matrix.T).max(axis=1)
            per_inst = np.maximum.reduceat(sim[:, self.row_order], self.group_starts, axis=1)
        out = []
        for r in range(len(texts)):
            order = np.argsort(-per_inst[r])[:k]
            top = [(self.inst_names[c], float(per_inst[r, c])) for c in order]
            s2 = top[1][1] if len(top) > 1 else -1.0
            out.append(CResult(top, top[0][1], top[0][1] - s2, float(none[r])))
        return out
