"""Synthetic stems covering the situations real sessions produce."""
from __future__ import annotations

import math

import numpy as np

SR = 44100


def _source(seconds: float, seed: int) -> np.ndarray:
    """Music-like mono source: decaying harmonic notes plus a bit of filtered noise."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    note_len = int(0.5 * SR)
    for start in range(0, n, note_len):
        f0 = 110 * 2 ** (rng.integers(0, 24) / 12)
        seg = t[: min(note_len, n - start)]
        env = np.exp(-seg * 4)
        tone = sum(np.sin(2 * math.pi * f0 * k * seg + rng.uniform(0, 6.28)) / k for k in range(1, 8))
        out[start:start + len(seg)] += tone * env
    noise = np.convolve(rng.standard_normal(n), np.ones(8) / 8, mode="same")
    out += 0.05 * noise
    return 0.3 * out / np.max(np.abs(out))


def _pan(s: np.ndarray, pan: float) -> np.ndarray:
    """Constant-power pan, -1 = left, +1 = right."""
    phi = (pan + 1) * math.pi / 4
    return np.stack([math.cos(phi) * s, math.sin(phi) * s], axis=1)


def _noise(n: int, level_db: float, seed: int) -> np.ndarray:
    return 10 ** (level_db / 20) * np.random.default_rng(seed).standard_normal(n)


def _decorrelated_reverb(s: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ir_len = int(0.6 * SR)
    decay = np.exp(-np.arange(ir_len) / SR * 8)
    decay /= np.sqrt(np.sum(decay ** 2))  # unit-energy impulse response
    return np.stack([np.convolve(s, rng.standard_normal(ir_len) * decay)[: len(s)] for _ in range(2)], axis=1)


def build_cases(seconds: float = 8.0) -> list[tuple[str, np.ndarray, str]]:
    s = _source(seconds, 1)
    n = len(s)
    cases: list[tuple[str, np.ndarray, str]] = []
    add = lambda name, x, expected: cases.append((name, np.asarray(x, dtype=np.float64), expected))

    add("centre mono (L = R)", np.stack([s, s], 1), "fake_stereo")
    add("mono panned 30% left", _pan(s, -0.3), "fake_stereo")
    add("mono panned 80% right", _pan(s, 0.8), "fake_stereo")
    add("hard left, right digital silence", np.stack([s, np.zeros(n)], 1), "hard_left")
    add("hard left, right = -65 dBFS noise", np.stack([s, _noise(n, -65, 2)], 1), "hard_left")
    add("hard right, left = -46 dB bleed", np.stack([0.005 * s, s], 1), "hard_right")
    add("polarity inverted (R = -L)", np.stack([s, -s], 1), "fake_stereo")
    gated = s * (np.arange(n) % int(2 * SR) < int(0.6 * SR))  # 70 % silence, like a sparse stem
    add("sparse mono stem (70% silence)", np.stack([gated, gated], 1), "fake_stereo")
    add("mono + -35 dB channel noise (lossy-like)",
        _pan(s, -0.2) + np.stack([_noise(n, -60, 3), _noise(n, -60, 4)], 1), "fake_stereo")
    add("mono + DC offset on left", np.stack([s + 0.02, s], 1), "fake_stereo")
    add("true stereo (two sources)", np.stack([s, _source(seconds, 7)], 1), "true_stereo")
    add("mono + wide stereo reverb", np.stack([s, s], 1) + 0.3 * _decorrelated_reverb(s, 5), "true_stereo")
    lag = int(0.012 * SR)
    add("Haas: right delayed 12 ms", np.stack([s, np.concatenate([np.zeros(lag), s[:-lag]])], 1), "delayed_mono")
    mixed = np.stack([s, s], 1)
    tail = slice(int(0.7 * n), n)
    mixed[tail, 1] = _source(seconds, 9)[tail]
    add("mono, last 30% true stereo", mixed, "true_stereo")
    return cases


def long_hard_left(minutes: float = 4.0, sr: int = 48000) -> np.ndarray:
    """Hard-left stem long enough to break the original absolute energy check."""
    reps = int(minutes * 60 / 8) + 1
    s = np.tile(_source(8.0, 11), reps)[: int(minutes * 60 * SR)]
    s = np.interp(np.arange(int(len(s) * sr / SR)) * SR / sr, np.arange(len(s)), s)
    return np.stack([s, np.zeros_like(s)], 1)
