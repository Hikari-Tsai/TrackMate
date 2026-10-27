"""Wires the pieces together: knowledge base, model downloads, lazily loaded C/D layers."""
from __future__ import annotations

import threading

from .audio import AudioClassifier
from .config import EngineConfig
from .embed import EmbeddingIndex, TextEmbedder
from .kb import KnowledgeBase
from .models import ModelManager
from .pipeline import Analyzer


class Engine:
    def __init__(self, config: EngineConfig | None = None, models: ModelManager | None = None):
        self.config = config or EngineConfig()
        self.kb = KnowledgeBase(self.config.kb_path, self.config.user_aliases_path)
        self.models = models or ModelManager(self.config.models_dir)
        self._lock = threading.Lock()
        self._index: EmbeddingIndex | None = None
        self._audio: AudioClassifier | None = None

    def _load_index(self) -> EmbeddingIndex | None:
        name = "qwen3_embedding"
        if self._index is None and self.models.is_ready(name):
            spec = self.models.specs[name]
            embedder = TextEmbedder(self.models.model_dir(name), spec.onnx)
            self._index = EmbeddingIndex(self.kb, embedder, self.config.cache_dir)
        return self._index

    def _load_audio(self) -> AudioClassifier | None:
        name = "peav_audio"
        if self._audio is None and self.models.is_ready(name):
            d = self.models.model_dir(name)
            self._audio = AudioClassifier(self.models.onnx_path(name), d / "scoring.json",
                                          settings=self.config.audio)
        return self._audio

    def analyzer(self) -> Analyzer:
        """Uses whatever layers are available now; C and D join once their models are ready."""
        with self._lock:
            return Analyzer(self.kb, self._load_index(), self._load_audio(), self.config.thresholds)

    def layers(self) -> dict:
        return {"A": True, "B": True, "C": self._index is not None or self.models.is_ready("qwen3_embedding"),
                "D": self._audio is not None or self.models.is_ready("peav_audio")}

    def add_feedback(self, name: str, instrument: str) -> str:
        key = self.kb.add_user_alias(name, instrument)
        with self._lock:
            if self._index is not None:
                self._index.rebuild()
        return key
