"""Layer D (README: Recognition pipeline): PE-AV audio encoder (ONNX) against precomputed text prototypes.

Only the category is decided here. Preprocessing: mono at 48 kHz, skip silence, take the
loudest non-overlapping segments, embed each, average, then score every class with PE-AV's own
logit (scale * dot + bias) and softmax over the classes for a ranking.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

from .config import DATA_DIR, AudioSettings

HOP = 1920  # PE-AV feature extractor: input length must be a multiple of 1920 samples


@dataclass
class DResult:
    ranking: list[tuple[str, float]]          # (class key, probability), best first
    categories: dict[str, float]              # KB category -> summed probability (traps excluded)
    best_category: str | None
    best_instrument: str | None
    best_prob: float
    segments: int
    silent: bool = False
    notes: list[str] = field(default_factory=list)


def read_mono(path: str, sr: int) -> np.ndarray:
    import soxr
    x, rate = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if rate != sr:
        x = soxr.resample(x, rate, sr).astype(np.float32)
    return x


def loudest_segments(x: np.ndarray, sr: int, seconds: float, count: int, silence_db: float) -> list[np.ndarray]:
    """Non-overlapping windows with the most energy, skipping windows below the silence level."""
    seg = int(seconds * sr)
    if len(x) <= seg:
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        return [x] if rms > 0 and 20 * np.log10(rms) > silence_db else []
    hop = sr  # 1 s grid
    n = (len(x) - seg) // hop + 1
    power = np.convolve(x.astype(np.float64) ** 2, np.ones(hop), "valid")[::hop]  # per-second energy
    per_window = np.array([power[i:i + int(seconds)].sum() for i in range(n)]) / seg
    order = np.argsort(-per_window)
    picked: list[int] = []
    for i in order:
        if len(picked) == count:
            break
        if 10 * np.log10(per_window[i] + 1e-20) < silence_db:
            break
        if all(abs(int(i) - p) * hop >= seg for p in picked):
            picked.append(int(i))
    return [x[p * hop:p * hop + seg] for p in sorted(picked)]


class AudioClassifier:
    def __init__(self, onnx_path: pathlib.Path, scoring_path: pathlib.Path,
                 prototypes_path: pathlib.Path = DATA_DIR / "peav_prototypes.npz",
                 settings: AudioSettings = AudioSettings()):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        scoring = json.loads(scoring_path.read_text())
        self.scale = float(scoring["logit_scale"])
        self.bias = float(scoring["logit_bias"])
        data = np.load(prototypes_path, allow_pickle=False)
        self.classes = data["classes"].tolist()
        self.class_category = data["categories"].tolist()
        self.class_instrument = data["instruments"].tolist()
        self.prototypes = data["prototypes"].astype(np.float32)
        self.settings = settings

    def embed(self, segment: np.ndarray) -> np.ndarray:
        pad = (-len(segment)) % HOP
        if pad:
            segment = np.pad(segment, (0, pad), mode="reflect" if len(segment) > pad else "constant")
        return self.sess.run(["audio_embedding"], {"input_values": segment[None, None, :].astype(np.float32)})[0][0]

    def classify(self, path: str) -> DResult:
        s = self.settings
        x = read_mono(path, s.sample_rate)
        segments = loudest_segments(x, s.sample_rate, s.segment_seconds, s.max_segments, s.silence_db)
        if not segments:
            return DResult([], {}, None, None, 0.0, 0, silent=True, notes=["no audio above the silence level"])
        emb = np.mean([self.embed(seg) for seg in segments], axis=0)
        logits = self.prototypes @ emb * self.scale + self.bias
        p = np.exp(logits - logits.max())
        p /= p.sum()
        order = np.argsort(-p)
        ranking = [(self.classes[i], float(p[i])) for i in order]
        cats: dict[str, float] = {}
        for i, c in enumerate(self.class_category):
            if c:
                cats[c] = cats.get(c, 0.0) + float(p[i])
        top = int(order[0])
        return DResult(ranking, dict(sorted(cats.items(), key=lambda kv: -kv[1])),
                       self.class_category[top] or None, self.class_instrument[top] or None,
                       float(p[top]), len(segments))
