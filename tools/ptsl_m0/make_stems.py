"""Write a small set of synthetic stems for the M0 PTSL import test.

The files cover the cases the importer must handle: mono and stereo files, a stereo file
with content only on the left, a non-ASCII file name, and a sample rate that differs from
the session (44.1 kHz into a 48 kHz session).

Usage: python make_stems.py OUT_DIR
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import soundfile as sf

SECONDS = 8


def tone(sr: int, freqs: list[float], decay: float = 0.0, period: float = 0.0) -> np.ndarray:
    t = np.arange(SECONDS * sr) / sr
    x = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    if period:
        x = x * np.exp(-decay * (t % period))
    return (0.3 * x).astype(np.float32)


def main() -> int:
    out = pathlib.Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    sr = 48000
    kick = tone(sr, [55], decay=30, period=0.5)
    snare = (rng.standard_normal(SECONDS * sr).astype(np.float32) * 0.2) * np.exp(
        -40 * ((np.arange(SECONDS * sr) / sr + 0.25) % 0.5)).astype(np.float32)
    piano = tone(sr, [261.6, 329.6, 392.0], decay=2, period=2.0)
    guitar = tone(sr, [196.0, 246.9], decay=3, period=1.0)
    files = {
        "Kick In.wav": (kick, sr),
        "SNR_Top.wav": (snare, sr),
        "OH.wav": (np.stack([snare * 0.6, snare * 0.5 + kick * 0.2], axis=1), sr),
        "Bass DI.wav": (tone(sr, [41.2, 82.4]), sr),
        "鋼琴.wav": (np.stack([piano, piano * 0.8], axis=1), sr),
        "Gtr L only.wav": (np.stack([guitar, np.zeros_like(guitar)], axis=1), sr),
        "Lead Vox 44k.wav": (tone(44100, [220.0, 440.0], decay=1, period=1.0), 44100),
    }
    for name, (data, rate) in files.items():
        sf.write(out / name, data, rate, subtype="PCM_24")
        print(f"{name}: {rate} Hz, {1 if data.ndim == 1 else data.shape[1]} ch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
