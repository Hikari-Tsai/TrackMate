"""Paths and tunable thresholds for the engine.

Thresholds are starting values from the experiments in experiments/c_layer_embedding and
experiments/instrument_zeroshot; they are recalibrated on real labelled sessions.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, field

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
REPO_ROOT = PACKAGE_DIR.parents[1]


def default_kb_path() -> pathlib.Path:
    bundled = DATA_DIR / "mix_naming.json"
    return bundled if bundled.exists() else REPO_ROOT / "kb" / "mix_naming.json"


def default_home() -> pathlib.Path:
    """Per-user state: downloaded models, user aliases, caches, the API token."""
    env = os.environ.get("STEM_ENGINE_HOME")
    if env:
        return pathlib.Path(env)
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support"
    else:
        base = pathlib.Path(os.environ.get("XDG_DATA_HOME") or pathlib.Path.home() / ".local" / "share")
    return base / "TrackMate"


@dataclass(frozen=True)
class Thresholds:
    # B layer (rapidfuzz WRatio on aliases)
    fuzzy_min_score: float = 90.0
    fuzzy_min_length: int = 4
    fuzzy_min_margin: float = 5.0
    # C layer (Qwen3 cosine). s1 = best instrument score, margin = s1 - best other instrument,
    # none_margin = s1 - best NONE anchor. c_high 0.86 + margin 0.03: no non-instrument name
    # auto-renamed on testset_realistic (engine/tools/eval_text.py --sweep).
    c_high: float = 0.86
    c_high_margin: float = 0.03
    c_low: float = 0.62
    c_none_margin: float = 0.0
    # D layer (PE-AV): minimum softmax probability of the best class (16 classes, so chance is
    # 0.06). On Medley-solos clips 0.15 answers 99 % of clips with 98 % category accuracy.
    d_min_prob: float = 0.15


@dataclass(frozen=True)
class AudioSettings:
    sample_rate: int = 48000
    segment_seconds: float = 10.0
    max_segments: int = 2
    silence_db: float = -60.0


@dataclass
class EngineConfig:
    home: pathlib.Path = field(default_factory=default_home)
    kb_path: pathlib.Path = field(default_factory=default_kb_path)
    thresholds: Thresholds = field(default_factory=Thresholds)
    audio: AudioSettings = field(default_factory=AudioSettings)
    # PTSL address; tests point it at a closed port to simulate "Pro Tools is not running".
    ptsl_address: str = field(default_factory=lambda: os.environ.get("STEM_ENGINE_PTSL", "localhost:31416"))

    @property
    def models_dir(self) -> pathlib.Path:
        return self.home / "models"

    @property
    def cache_dir(self) -> pathlib.Path:
        return self.home / "cache"

    @property
    def user_aliases_path(self) -> pathlib.Path:
        return self.home / "user_aliases.json"
