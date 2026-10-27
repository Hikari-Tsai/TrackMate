"""Stereo handling for /analyze and /apply, built on stereo_analysis/stereo_analyzer.py."""
from __future__ import annotations

import pathlib

from stereo_analyzer import Action, StereoAnalysis, analyze, write_downmix


def summarize(a: StereoAnalysis) -> dict:
    return {
        "type": a.stereo_type.value,
        "action": a.action.value,
        "confidence": a.confidence,
        "channels": a.channels,
        "sample_rate": a.sample_rate,
        "duration_seconds": round(a.duration_seconds, 3),
        "pan": None if a.pan is None else round(a.pan, 3),
        "polarity_inverted": a.polarity_inverted,
        "delay_ms": a.delay_ms,
        "notes": a.notes,
    }


def analyze_file(path: str) -> dict:
    return summarize(analyze(path))


def to_mono(path: str, out_dir: pathlib.Path) -> str | None:
    """Write the recommended mono file; None when the file should stay as it is."""
    a = analyze(path)
    if a.action is Action.KEEP:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    return write_downmix(a, str(out_dir / pathlib.Path(path).name))
