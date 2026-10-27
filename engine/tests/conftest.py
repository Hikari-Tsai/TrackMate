import os
import pathlib

import numpy as np
import pytest
import soundfile as sf

from stem_engine.config import EngineConfig, default_kb_path
from stem_engine.kb import KnowledgeBase

DEV_HOME = pathlib.Path(os.environ.get("STEM_ENGINE_DEV_HOME", pathlib.Path(__file__).resolve().parents[2]
                                       / "build" / "engine_home"))


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase(default_kb_path())


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


@pytest.fixture
def config(home):
    return EngineConfig(home=home)


def write_tone(path: pathlib.Path, seconds: float = 2.0, sr: int = 48000, channels: int = 1, freq: float = 220.0):
    t = np.arange(int(seconds * sr)) / sr
    x = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    data = x if channels == 1 else np.stack([x] * channels, axis=1)
    sf.write(path, data, sr, subtype="PCM_24")
    return path


@pytest.fixture
def stems(tmp_path):
    d = tmp_path / "stems"
    d.mkdir()
    return {name: str(write_tone(d / name, channels=ch)) for name, ch in
            [("Kick In_03.wav", 1), ("OH.wav", 2), ("鋼琴.wav", 2), ("Audio 7.wav", 1), ("Gtr Fuzz.wav", 1)]}
