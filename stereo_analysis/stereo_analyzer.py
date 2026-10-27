"""Stereo / mono detection for multitrack stems.

The question we answer for every 2-channel file is: "is this really one mono
source, and if so, how do we get it back without changing its level or sound?"

A single mono source placed in a stereo file -- whatever the pan position,
pan law or polarity -- always satisfies  L(t) = a*s(t),  R(t) = b*s(t).
Geometrically the (L, R) sample cloud collapses onto one line through the
origin. So instead of comparing L and R directly (which breaks as soon as the
source is panned), we measure how "rank-1" the 2x2 covariance matrix is:

    residual_db = 10*log10(lambda_min / lambda_max)

  * identical or panned mono   -> residual is very low (-60 dB or below)
  * mono with polarity flipped -> also low (the line just has negative slope)
  * real stereo / reverb / XY  -> residual is high (typically > -20 dB)

The principal eigenvector gives the pan position and polarity, and projecting
onto it gives a downmix that never cancels and keeps the loudest channel's
level. Everything is computed only on "active" frames (above an absolute gate
and within a relative range of the loudest frame), so long silences, fades and
dither noise no longer bias the result.
"""
from __future__ import annotations

import argparse
import enum
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field

import numpy as np
import soundfile as sf

_EPS = 1e-20


class StereoType(str, enum.Enum):
    MONO_FILE = "mono_file"            # already 1 channel
    SILENT = "silent"                  # nothing above the gate
    FAKE_STEREO = "fake_stereo"        # one source, any pan/polarity
    HARD_LEFT = "hard_left"            # right channel is (effectively) empty
    HARD_RIGHT = "hard_right"          # left channel is (effectively) empty
    DELAYED_MONO = "delayed_mono"      # same source with a time offset (Haas)
    TRUE_STEREO = "true_stereo"
    MULTICHANNEL = "multichannel"      # > 2 channels, not handled


class Action(str, enum.Enum):
    KEEP = "keep"
    TAKE_LEFT = "take_left"
    TAKE_RIGHT = "take_right"
    DOWNMIX = "downmix"


@dataclass(frozen=True)
class Settings:
    frame_seconds: float = 0.1
    # A frame counts as active when it is above this absolute level ...
    absolute_gate_db: float = -70.0
    # ... and no more than this far below the loudest frame.
    relative_gate_db: float = 50.0
    # The weaker channel must sit this far below the stronger one to be ignored
    # (30 dB down is inaudible next to the other side, whatever it contains).
    hard_pan_db: float = 30.0
    # Covariance residual below which the file is treated as one source.
    # -30 dB tolerates lossy codecs (MP3/AAC) and low noise floors.
    mono_residual_db: float = -30.0
    # Individual frames are noisier, so they get some extra headroom.
    frame_residual_margin_db: float = 10.0
    # Share of active energy that must look mono (guards against a mono part
    # followed by a genuinely stereo section).
    mono_energy_fraction: float = 0.95
    # Time-offset (Haas / spaced-mic) detection.
    max_delay_ms: float = 30.0
    delay_correlation: float = 0.9
    delay_probe_windows: int = 8


@dataclass
class StereoAnalysis:
    path: str
    stereo_type: StereoType
    action: Action
    confidence: str
    channels: int
    sample_rate: int
    duration_seconds: float
    active_seconds: float = 0.0
    left_db: float | None = None
    right_db: float | None = None
    balance_db: float | None = None        # right minus left, active frames
    correlation: float | None = None       # zero-lag Pearson, active frames
    residual_db: float | None = None       # rank-1 residual (lower = more mono)
    mono_energy_fraction: float | None = None
    pan: float | None = None               # -1 = left, 0 = centre, +1 = right
    polarity_inverted: bool = False
    delay_ms: float | None = None
    downmix_weights: tuple[float, float] | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stereo_type"] = self.stereo_type.value
        d["action"] = self.action.value
        return d


def _db(power: float) -> float:
    return 10.0 * math.log10(max(power, _EPS))


def _frame_stats(path: str, frame_len: int) -> dict[str, np.ndarray]:
    """Per-frame second-order statistics, streamed so long files stay cheap."""
    keys = ("n", "sum_l", "sum_r", "pll", "prr", "plr")
    parts: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    with sf.SoundFile(path) as f:
        for block in f.blocks(blocksize=frame_len * 256, dtype="float64", always_2d=True):
            l_all, r_all = block[:, 0], block[:, 1]
            full = len(block) // frame_len * frame_len
            chunks = []
            if full:
                chunks.append((l_all[:full].reshape(-1, frame_len), r_all[:full].reshape(-1, frame_len)))
            if len(block) - full >= frame_len // 4:  # keep a meaningful tail
                chunks.append((l_all[full:][None, :], r_all[full:][None, :]))
            for l, r in chunks:
                parts["n"].append(np.full(len(l), l.shape[1], dtype=np.float64))
                parts["sum_l"].append(l.sum(1))
                parts["sum_r"].append(r.sum(1))
                parts["pll"].append((l * l).sum(1))
                parts["prr"].append((r * r).sum(1))
                parts["plr"].append((l * r).sum(1))
    return {k: np.concatenate(v) if v else np.zeros(0) for k, v in parts.items()}


def _principal_axis(cll, crr, clr):
    """Eigen-decomposition of [[cll, clr], [clr, crr]] (vectorised)."""
    half_trace = (cll + crr) / 2
    disc = np.sqrt(((cll - crr) / 2) ** 2 + clr ** 2)
    lam_max = half_trace + disc
    lam_min = np.maximum(half_trace - disc, 0.0)
    theta = 0.5 * np.arctan2(2 * clr, cll - crr)  # angle of the major axis from L
    return lam_max, lam_min, theta


def _estimate_delay(path: str, starts: list[int], win: int, max_lag: int) -> tuple[float, int] | None:
    """Best normalised cross-correlation at a non-zero lag over a few loud windows."""
    peaks, lags = [], []
    with sf.SoundFile(path) as f:
        for start in starts:
            f.seek(max(start, 0))
            x = f.read(win, dtype="float64", always_2d=True)
            if len(x) < win // 2:
                continue
            l, r = x[:, 0] - x[:, 0].mean(), x[:, 1] - x[:, 1].mean()
            norm = math.sqrt(float(l @ l) * float(r @ r))
            if norm < _EPS:
                continue
            n = 1 << (2 * len(l) - 1).bit_length()
            xc = np.fft.irfft(np.fft.rfft(r, n) * np.conj(np.fft.rfft(l, n)), n)
            # positive lag = right channel arrives later
            window = np.concatenate([xc[-max_lag:], xc[: max_lag + 1]]) / norm
            k = int(np.argmax(np.abs(window)))
            peaks.append(float(window[k]))
            lags.append(k - max_lag)
    if not lags:
        return None
    lag = int(np.median(lags))
    agreeing = [abs(p) for p, g in zip(peaks, lags) if abs(g - lag) <= 1]
    if len(agreeing) < max(1, len(lags) // 2):
        return None
    return float(np.median(agreeing)), lag


def analyze(path: str, settings: Settings = Settings()) -> StereoAnalysis:
    info = sf.info(path)
    base = dict(path=path, channels=info.channels, sample_rate=info.samplerate,
                duration_seconds=info.frames / info.samplerate if info.samplerate else 0.0)
    if info.channels == 1:
        return StereoAnalysis(stereo_type=StereoType.MONO_FILE, action=Action.KEEP, confidence="high", **base)
    if info.channels != 2:
        return StereoAnalysis(stereo_type=StereoType.MULTICHANNEL, action=Action.KEEP, confidence="high", **base)

    frame_len = max(1, int(round(settings.frame_seconds * info.samplerate)))
    st = _frame_stats(path, frame_len)
    n = st["n"]
    if n.size == 0:
        return StereoAnalysis(stereo_type=StereoType.SILENT, action=Action.KEEP, confidence="high", **base)

    # Mean-removed (co)variances per frame: DC offsets must not look like width.
    cll = st["pll"] - st["sum_l"] ** 2 / n
    crr = st["prr"] - st["sum_r"] ** 2 / n
    clr = st["plr"] - st["sum_l"] * st["sum_r"] / n
    frame_db = 10 * np.log10(np.maximum((st["pll"] + st["prr"]) / (2 * n), _EPS))
    active = (frame_db > settings.absolute_gate_db) & (frame_db > frame_db.max() - settings.relative_gate_db)

    result = StereoAnalysis(stereo_type=StereoType.TRUE_STEREO, action=Action.KEEP, confidence="medium", **base)
    result.active_seconds = float(n[active].sum() / info.samplerate)
    if not active.any():
        result.stereo_type, result.confidence = StereoType.SILENT, "high"
        result.notes.append("no frame above the gate")
        return result

    a_ll, a_rr, a_lr = cll[active].sum(), crr[active].sum(), clr[active].sum()
    n_active = n[active].sum()
    result.left_db = round(_db(st["pll"][active].sum() / n_active), 2)
    result.right_db = round(_db(st["prr"][active].sum() / n_active), 2)
    balance = _db(a_rr) - _db(a_ll)
    result.balance_db = round(balance, 2)
    result.correlation = round(float(a_lr / math.sqrt(max(a_ll * a_rr, _EPS))), 4)

    # 1) One channel is effectively empty: no correlation needed at all.
    if abs(balance) >= settings.hard_pan_db:
        left_side = balance < 0
        result.stereo_type = StereoType.HARD_LEFT if left_side else StereoType.HARD_RIGHT
        result.action = Action.TAKE_LEFT if left_side else Action.TAKE_RIGHT
        result.downmix_weights = (1.0, 0.0) if left_side else (0.0, 1.0)
        result.pan = -1.0 if left_side else 1.0
        result.confidence = "high" if abs(balance) >= settings.hard_pan_db + 10 else "medium"
        return result

    # 2) Rank-1 test on the active frames.
    lam_max, lam_min, theta = _principal_axis(a_ll, a_rr, a_lr)
    residual = _db(lam_min) - _db(lam_max)
    result.residual_db = round(residual, 2)

    f_max, f_min, _ = _principal_axis(cll[active], crr[active], clr[active])
    frame_resid = 10 * np.log10(np.maximum(f_min, _EPS) / np.maximum(f_max, _EPS))
    energy = (cll + crr)[active]
    mono_like = frame_resid < settings.mono_residual_db + settings.frame_residual_margin_db
    fraction = float(energy[mono_like].sum() / max(energy.sum(), _EPS))
    result.mono_energy_fraction = round(fraction, 4)

    cos_t, sin_t = math.cos(theta), math.sin(theta)
    result.pan = round((abs(theta) - math.pi / 4) / (math.pi / 4), 3)
    result.polarity_inverted = bool(cos_t * sin_t < 0 and min(abs(cos_t), abs(sin_t)) > 0.1)

    if residual < settings.mono_residual_db and fraction >= settings.mono_energy_fraction:
        result.stereo_type, result.action = StereoType.FAKE_STEREO, Action.DOWNMIX
        result.confidence = "high" if residual < settings.mono_residual_db - 15 else "medium"
        # Project onto the source axis, scaled so the result has the level of the
        # louder channel; keep the louder channel's polarity.
        gain = max(abs(cos_t), abs(sin_t))
        wl, wr = cos_t * gain, sin_t * gain
        if (abs(wl) >= abs(wr) and wl < 0) or (abs(wr) > abs(wl) and wr < 0):
            wl, wr = -wl, -wr
        result.downmix_weights = (round(wl, 6), round(wr, 6))
        if result.polarity_inverted:
            result.notes.append("channels are polarity-inverted copies; a plain L+R sum would cancel")
        return result

    if residual < settings.mono_residual_db:
        result.notes.append(
            f"mostly mono overall but only {fraction:.0%} of the active energy is mono; kept as stereo")

    # 3) Same source with a time offset? Only probe when it is not already mono.
    max_lag = max(1, int(settings.max_delay_ms / 1000 * info.samplerate))
    win = max(frame_len, 16 * max_lag)
    loud = np.argsort(np.where(active, frame_db, -np.inf))[::-1][: settings.delay_probe_windows]
    starts = [int(i) * frame_len - (win - frame_len) // 2 for i in loud if active[i]]
    delay = _estimate_delay(path, starts, win, max_lag)
    if delay is not None:
        peak, lag = delay
        if lag != 0 and abs(peak) >= settings.delay_correlation:
            result.stereo_type = StereoType.DELAYED_MONO
            result.delay_ms = round(lag / info.samplerate * 1000, 3)
            result.notes.append("one channel is a delayed copy of the other; summing would comb-filter, so it is kept")
            result.confidence = "medium"
            return result

    result.confidence = "high" if residual > settings.mono_residual_db + 10 else "medium"
    return result


def write_downmix(analysis: StereoAnalysis, out_path: str, block_frames: int = 1 << 16) -> str:
    """Write the mono version recommended by `analyze` (same format/subtype)."""
    if analysis.action is Action.KEEP or analysis.downmix_weights is None:
        raise ValueError(f"{analysis.path}: nothing to convert ({analysis.stereo_type.value})")
    wl, wr = analysis.downmix_weights
    with sf.SoundFile(analysis.path) as src:
        with sf.SoundFile(out_path, "w", samplerate=src.samplerate, channels=1,
                          format=src.format, subtype=src.subtype) as dst:
            for block in src.blocks(blocksize=block_frames, dtype="float64", always_2d=True):
                dst.write(block[:, 0] * wl + block[:, 1] * wr)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect fake stereo / hard-panned stems.")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--convert", metavar="DIR", help="write mono versions of convertible files here")
    parser.add_argument("--mono-residual-db", type=float, default=Settings.mono_residual_db)
    parser.add_argument("--hard-pan-db", type=float, default=Settings.hard_pan_db)
    args = parser.parse_args(argv)

    settings = Settings(mono_residual_db=args.mono_residual_db, hard_pan_db=args.hard_pan_db)
    for path in args.files:
        a = analyze(path, settings)
        record = a.to_dict()
        if args.convert and a.action is not Action.KEEP:
            os.makedirs(args.convert, exist_ok=True)
            stem, ext = os.path.splitext(os.path.basename(path))
            record["output"] = write_downmix(a, os.path.join(args.convert, f"{stem}_mono{ext}"))
        print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
