"""Tempo detection (README: Tempo): Beat This! (ONNX) on a mono mix of the rhythm stems, then a
constant BPM or a tempo map, written as a tempo-only MIDI file that Pro Tools imports.

Beat This! (Foscarin, Schlüter, Widmer, ISMIR 2024) predicts beat and downbeat logits from a
log-mel spectrogram at 50 frames per second. The frontend, chunking and peak picking follow
the reference implementation (CPJKU/beat_this, "minimal" postprocessing); peaks are then
refined to sub-frame precision so beat gaps are not quantised to 20 ms.

Beats are read as quarter notes: a song felt in half or double time is detected as such, so
the app offers x0.5 and x2.
"""
from __future__ import annotations

import json
import pathlib
import struct
import time
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 22050
FPS = 50                    # 22050 / 441
CHUNK, BORDER = 1500, 6     # frames per model call, frames dropped at each chunk edge
PPQ = 480                   # MIDI ticks per quarter note
STEADY_SECONDS = 0.03       # every beat within 30 ms of one straight grid = constant tempo
MAX_SECONDS = 20 * 60

DRUM_CATEGORIES = ("drums", "percussion")
RHYTHM_CATEGORIES = ("bass", "guitars", "keys", "synths")


class NoBeats(ValueError):
    """Too short, silent, or no steady pulse found."""


# ------------------------------------------------------------------ sources
def pick_sources(tracks: list[dict]) -> tuple[str, list[str]]:
    """Drums and percussion when there are any, else the other rhythm section, else everything."""
    for kind, cats in (("drums", DRUM_CATEGORIES), ("rhythm", RHYTHM_CATEGORIES)):
        files = [t["file"] for t in tracks if t.get("category") in cats]
        if files:
            return kind, files
    return "all", [t["file"] for t in tracks]


def mix(files: list[str]) -> np.ndarray:
    """Mono sum at 22.05 kHz, stems aligned at their start. The level is kept (the log-mel
    frontend is level dependent: raising a quiet mix to full scale adds false beats) and only
    lowered when the sum would clip."""
    from .audio import read_mono
    parts = [read_mono(f, SAMPLE_RATE)[:MAX_SECONDS * SAMPLE_RATE] for f in files]
    out = np.zeros(max((len(p) for p in parts), default=0), dtype=np.float32)
    for p in parts:
        out[:len(p)] += p
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    return out / peak if peak > 1 else out


# ------------------------------------------------------------------ model
class BeatTracker:
    def __init__(self, onnx_path: pathlib.Path, frontend_path: pathlib.Path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        f = json.loads(frontend_path.read_text())
        assert f["sample_rate"] == SAMPLE_RATE and f["hop_length"] * FPS == SAMPLE_RATE
        self.n_fft, self.hop = int(f["n_fft"]), int(f["hop_length"])
        self.window = np.asarray(f["window"], dtype=np.float32)
        self.filters = np.asarray(f["mel_filters"], dtype=np.float32).T   # [n_fft/2+1, 128]

    def log_mel(self, x: np.ndarray) -> np.ndarray:
        """torchaudio MelSpectrogram as trained: centred frames (reflect padding), periodic Hann,
        magnitude / sqrt(n_fft), Slaney mel filters, then log1p(1000 * mel)."""
        n, hop = self.n_fft, self.hop
        frames = len(x) // hop + 1
        padded = np.pad(x, n // 2, mode="reflect")
        windows = np.lib.stride_tricks.sliding_window_view(padded, n)[::hop][:frames]
        out = np.empty((frames, self.filters.shape[1]), dtype=np.float32)
        for s in range(0, frames, 2048):
            mag = np.abs(np.fft.rfft(windows[s:s + 2048] * self.window, axis=1)) / np.sqrt(n)
            out[s:s + 2048] = np.log1p(1000 * (mag.astype(np.float32) @ self.filters))
        return out

    def logits(self, spect: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Overlapping chunks of 1500 frames; the 6 border frames of each are discarded and
        earlier chunks win where two overlap (the reference's keep_first)."""
        frames = len(spect)
        starts = list(range(-BORDER, frames - BORDER, CHUNK - 2 * BORDER))
        if frames > CHUNK - 2 * BORDER:
            starts[-1] = frames - (CHUNK - BORDER)
        beat = np.full(frames, -1000, dtype=np.float32)
        down = np.full(frames, -1000, dtype=np.float32)
        for start in reversed(starts):
            left, right = max(0, -start), max(0, min(BORDER, start + CHUNK - frames))
            chunk = spect[max(0, start):min(start + CHUNK, frames)]
            chunk = np.pad(chunk, ((left, right), (0, 0)))
            b, d = self.sess.run(["beat", "downbeat"], {"spectrogram": chunk[None]})
            keep = slice(BORDER, len(chunk) - BORDER)
            pos = np.arange(len(chunk))[keep] + start
            ok = (pos >= 0) & (pos < frames)
            beat[pos[ok]], down[pos[ok]] = b[0][keep][ok], d[0][keep][ok]
        return beat, down

    def track(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Beat and downbeat times in seconds."""
        if len(x) < 2 * SAMPLE_RATE or not np.any(np.abs(x) >= 1e-7):
            return np.array([]), np.array([])
        beat, down = self.logits(self.log_mel(x))
        beats, downs = peaks(beat), peaks(down)
        if len(beats):  # downbeats are beats: snap each to the nearest one
            downs = np.unique(beats[np.abs(beats[None, :] - downs[:, None]).argmin(axis=1)]) if len(downs) else downs
        return beats, downs


def peaks(logits: np.ndarray) -> np.ndarray:
    """Local maxima above 0 within +-3 frames, neighbours merged (reference), then each
    refined by a parabola through the peak frame and its neighbours."""
    n = len(logits)
    padded = np.pad(logits, 3, constant_values=-np.inf)
    local_max = np.lib.stride_tricks.sliding_window_view(padded, 7).max(axis=1)
    candidates = np.flatnonzero((logits > 0) & (logits == local_max))
    merged: list[float] = []
    mean, count = None, 0
    for p in candidates:
        if mean is not None and p - mean <= 1:
            count += 1
            mean += (p - mean) / count
        else:
            if mean is not None:
                merged.append(mean)
            mean, count = float(p), 1
    if mean is not None:
        merged.append(mean)
    out = []
    for m in merged:
        i = int(round(m))
        offset = m - i
        if m == i and 0 < i < n - 1:
            a, b, c = float(logits[i - 1]), float(logits[i]), float(logits[i + 1])
            denom = a - 2 * b + c
            if denom < 0:
                offset = float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5))
        out.append((i + offset) / FPS)
    return np.asarray(out, dtype=np.float64)


# ------------------------------------------------------------------ tempo
def regularize(beats: np.ndarray, downbeats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Make the beats one quarter note apart throughout, measured against the song's main beat
    gap (the median): a beat closer than 0.7 gaps to the previous one is dropped (a passage
    tracked in double time, a flam), and where the stems pause the missing beats are put back
    evenly. Without this one double-time intro or a drum break would read as a tempo change.
    Tempo changes of more than about 30 % within a song are therefore not followed."""
    beats = np.asarray(beats, dtype=np.float64)
    if len(beats) < 3:
        return beats, np.asarray(downbeats, dtype=np.float64)
    gap = float(np.median(np.diff(beats)))
    kept = [beats[0]]
    for b in beats[1:]:
        if b - kept[-1] >= 0.7 * gap:
            kept.append(b)
    out = [kept[0]]
    for b in kept[1:]:
        missing = int(round((b - out[-1]) / gap)) - 1
        if missing > 0:
            out.extend(np.linspace(out[-1], b, missing + 2)[1:-1])
        out.append(b)
    out = np.asarray(out)
    downs = np.asarray(downbeats, dtype=np.float64)
    if len(downs):  # dropped downbeats move to the nearest remaining beat
        downs = np.unique(out[np.abs(out[None, :] - downs[:, None]).argmin(axis=1)])
    return out, downs


def scale_beats(beats: np.ndarray, factor: float) -> np.ndarray:
    """x0.5: every other beat. x2: a beat between each pair."""
    beats = np.asarray(beats, dtype=np.float64)
    if factor == 0.5:
        return beats[::2]
    if factor == 2 and len(beats) >= 2:
        mid = (beats[:-1] + beats[1:]) / 2
        return np.sort(np.concatenate([beats, mid]))
    return beats


def meter(beats: np.ndarray, downbeats: np.ndarray) -> int | None:
    """Beats per bar when every bar has the same count."""
    if len(downbeats) < 3 or len(beats) < 2:
        return None
    idx = np.searchsorted(beats, downbeats - 1e-6)
    if (idx >= len(beats)).any() or not np.allclose(beats[idx], downbeats, atol=1e-6):
        return None
    bars = np.diff(idx)
    return int(bars[0]) if 1 <= bars[0] <= 16 and (bars == bars[0]).all() else None


def segments(beats: np.ndarray, downbeats: np.ndarray) -> list[int]:
    """Beat indices where the tempo map may change: each detected bar line, or every 4 beats
    when no downbeats were found. Tempo is constant inside a bar, so 20 ms jitter of single
    beats does not make the map shake and every bar line stays where it was detected."""
    n = len(beats)
    idx = sorted({int(i) for i in np.searchsorted(beats, np.asarray(downbeats) - 1e-6) if 0 < i < n - 1})
    if len(idx) < 2:
        idx = list(range(4, n - 1, 4))
    return [0, *idx, n - 1]


def analyse(beats: np.ndarray, downbeats: np.ndarray) -> dict:
    """BPM figures for the app. `bpm` is the average over the song (total time / beat gaps,
    so fast passages are not over-weighted); `steady` means one straight grid fits every beat."""
    beats = np.asarray(beats, dtype=np.float64)
    downbeats = np.asarray(downbeats, dtype=np.float64)
    if len(beats) < 5:
        raise NoBeats("fewer than 5 beats found")
    numbers = np.arange(len(beats))
    period, offset = np.polyfit(numbers, beats, 1)
    residual = float(np.max(np.abs(beats - (offset + period * numbers))))
    average = 60 * (len(beats) - 1) / (beats[-1] - beats[0])
    bounds = segments(beats, downbeats)
    bar_bpm = [60 * (j - i) / (beats[j] - beats[i]) for i, j in zip(bounds, bounds[1:])]
    steady = residual <= STEADY_SECONDS
    bpm = float(60 / period if steady else average)
    return {
        "bpm": round(bpm, 2),
        "bpm_rounded": int(round(bpm)),
        "bpm_min": round(float(min(bar_bpm)), 2),
        "bpm_max": round(float(max(bar_bpm)), 2),
        "steady": steady,
        "grid_error_ms": round(residual * 1000, 1),
        "suggested_mode": "constant" if steady else "variable",
        "signature_beats": meter(beats, downbeats),
        "beat_count": len(beats),
    }


def tempo_events(beats: np.ndarray, downbeats: np.ndarray, mode: str, bpm: float | None = None) -> list[tuple[int, int]]:
    """(tick, microseconds per quarter) events. Constant: one event. Variable: the first
    detected beat keeps its time from the session start, then one event per bar."""
    if mode == "constant":
        if not bpm or not 20 <= bpm <= 400:
            raise ValueError("constant tempo needs a BPM between 20 and 400")
        return [(0, round(60e6 / bpm))]
    beats = np.asarray(beats, dtype=np.float64)
    if len(beats) < 2:
        raise NoBeats("a tempo map needs at least 2 beats")
    bounds = segments(beats, downbeats)
    events: list[tuple[int, int]] = []
    for k, (i, j) in enumerate(zip(bounds, bounds[1:])):
        us = round((beats[j] - beats[i]) / (j - i) * 1e6)
        if k == 0:  # the time before the first beat runs at the first bar's tempo
            first_tick = round(beats[0] * 1e6 * PPQ / us)
            events.append((0, us))
            continue
        tick = first_tick + i * PPQ
        if us != events[-1][1]:
            events.append((tick, us))
    return events


def _vlq(value: int) -> bytes:
    out = [value & 0x7F]
    while value := value >> 7:
        out.insert(0, (value & 0x7F) | 0x80)
    return bytes(out)


def tempo_midi(events: list[tuple[int, int]], duration: float, beats_per_bar: int = 4) -> bytes:
    """Type 0 standard MIDI file with only tempo and time signature meta events (x/4)."""
    track = bytearray()
    prev, elapsed = 0, 0.0
    for k, (tick, us) in enumerate(events):
        if k:
            elapsed += (tick - prev) * events[k - 1][1] / PPQ / 1e6
        track += _vlq(tick - prev) + bytes([0xFF, 0x51, 3]) + us.to_bytes(3, "big")
        if k == 0:
            track += bytes([0, 0xFF, 0x58, 4, beats_per_bar, 2, 24, 8])
        prev = tick
    tail = max(0, round((duration - elapsed) * 1e6 * PPQ / events[-1][1]))
    track += _vlq(tail) + bytes([0xFF, 0x2F, 0])
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


def quarters_at(events: list[tuple[int, int]], seconds: float) -> float:
    """Position in quarter notes from the session start under these tempo events."""
    elapsed = 0.0
    for k, (tick, us) in enumerate(events):
        nxt = events[k + 1][0] if k + 1 < len(events) else None
        span = None if nxt is None else (nxt - tick) * us / PPQ / 1e6
        if span is None or seconds < elapsed + span:
            return tick / PPQ + (seconds - elapsed) * 1e6 / us
        elapsed += span
    raise AssertionError("unreachable")


def parse_bars_beats(text: str, beats_per_bar: int) -> float:
    """'   25| 2| 000' -> quarter notes from bar 1 (Pro Tools counts 960 ticks per quarter)."""
    bar, beat, tick = (int(v) for v in text.replace(" ", "").split("|"))
    return (bar - 1) * beats_per_bar + (beat - 1) + tick / 960


def midi_name(mode: str, bpm: float) -> str:
    return f"TrackMate Tempo {round(bpm)} BPM.mid" if mode == "constant" else f"TrackMate Tempo Map (avg {round(bpm)} BPM).mid"


def write_midi(data: bytes, name: str, folders: list[pathlib.Path]) -> pathlib.Path:
    """First folder that accepts the file (the stems' folder, else the engine's cache)."""
    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            path.write_bytes(data)
            return path
        except OSError:
            continue
    raise OSError("no folder accepted the MIDI file")


def bring_pro_tools_forward() -> None:
    """The MIDI Import Options dialog opens inside Pro Tools; show it to the user."""
    import subprocess
    import sys
    if sys.platform == "darwin":
        subprocess.run(["open", "-b", "com.avid.ProTools"], check=False, capture_output=True, timeout=10)


def import_to_pro_tools(midi: pathlib.Path, events: list[tuple[int, int]], beats_per_bar: int,
                        check_seconds: float, address: str, wait: float = 600) -> dict:
    """Import the tempo MIDI and verify it: the Bars|Beats position Pro Tools shows at
    `check_seconds` must match the one these tempo events give. `applied` is False when the
    user cancelled the dialog or left "Import tempo map from MIDI File" unticked."""
    from .protools import ProTools, ProToolsLost, call_with_timeout, is_connection_error
    with ProTools(address) as pro:
        session = call_with_timeout(pro.session, 10, "read session")
        bring_pro_tools_forward()
        try:
            call_with_timeout(lambda: pro.import_midi(str(midi), session["path"]), wait, "MIDI Import Options")
            sample = int(round(check_seconds * session["sample_rate"]))
            shown = call_with_timeout(lambda: pro.bars_beats_at(sample), 10, "read tempo")
        except Exception as exc:
            if is_connection_error(exc):
                raise ProToolsLost("Pro Tools stopped answering while importing the tempo") from exc
            raise
    expected = quarters_at(events, check_seconds)
    got = parse_bars_beats(shown, beats_per_bar)
    return {"applied": abs(got - expected) < 0.05, "check_seconds": round(check_seconds, 3),
            "expected_quarters": round(expected, 3), "pro_tools_position": shown.strip(),
            "pro_tools_quarters": round(got, 3)}


@dataclass
class Detection:
    source_kind: str
    sources: list[str]
    duration: float
    beats: np.ndarray
    downbeats: np.ndarray
    seconds: float

    def to_dict(self) -> dict:
        return {"source_kind": self.source_kind, "sources": self.sources, "duration": round(self.duration, 3),
                "seconds": round(self.seconds, 2), "beats": [round(float(b), 4) for b in self.beats],
                "downbeats": [round(float(d), 4) for d in self.downbeats],
                **analyse(self.beats, self.downbeats)}


def detect(tracker: BeatTracker, tracks: list[dict]) -> Detection:
    started = time.time()
    kind, files = pick_sources(tracks)
    x = mix(files)
    beats, downbeats = regularize(*tracker.track(x))
    if len(beats) < 5:
        raise NoBeats("no steady beat found in " + ("the drums" if kind == "drums" else "these stems"))
    return Detection(kind, files, len(x) / SAMPLE_RATE, beats, downbeats, time.time() - started)


def make_tempo(beats: list[float], downbeats: list[float], duration: float, mode: str, bpm: float | None,
               factor: float, signature_beats: int | None) -> tuple[list[tuple[int, int]], int, float, float]:
    """Tempo events for the user's choice. Returns (events, beats per bar, average BPM, the time
    used to verify the import: the last beat)."""
    b = scale_beats(np.asarray(beats, dtype=np.float64), factor)
    d = np.asarray(downbeats if factor == 1 else [], dtype=np.float64)
    if len(b) < 2 or (np.diff(b) <= 0).any():
        raise NoBeats("beats must be at least 2 increasing times")
    per_bar = signature_beats if factor == 1 and signature_beats else 4
    events = tempo_events(b, d, mode, bpm)
    average = bpm if mode == "constant" else 60 * (len(b) - 1) / (b[-1] - b[0])
    return events, per_bar, float(average), float(min(b[-1], duration))
