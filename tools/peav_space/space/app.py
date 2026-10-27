"""Zero-shot instrument recognition with the ONNX audio encoder of Meta PE-AV small.

The audio is embedded by aaatmy/pe-av-small-audio-ONNX. The text side is not in the ONNX
model, so every label's text embedding was computed offline with PE-AV's text encoder
(prototypes.npz, built by build_prototypes.py in the TrackMate repo).
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import time

import gradio as gr
import numpy as np
import onnxruntime as ort
import soundfile as sf
import soxr
from huggingface_hub import hf_hub_download

HERE = pathlib.Path(__file__).resolve().parent
REPO = "aaatmy/pe-av-small-audio-ONNX"
REVISION = "299615edbe5bc29d44d50cacd0e25ad69088f22b"
MODELS = {"8-bit (model_q8.onnx, 222 MB)": "onnx/model_q8.onnx",
          "float32 (model.onnx, 470 MB)": "onnx/model.onnx"}
SR = 48000
HOP = 1920  # input length must be a multiple of 1920 samples
MAX_SECONDS = 600  # decode at most the first 10 minutes
SILENCE_DB = -60.0

scoring = json.loads(pathlib.Path(hf_hub_download(REPO, "scoring.json", revision=REVISION)).read_text())
SCALE, BIAS = float(scoring["logit_scale"]), float(scoring["logit_bias"])

data = np.load(HERE / "prototypes.npz", allow_pickle=False)
KEYS = data["keys"].tolist()
EN, ZH, FAMILY = data["en"].tolist(), data["zh"].tolist(), data["family"].tolist()
PROTOTYPES = data["prototypes"].astype(np.float32)
FAMILY_ZH = json.loads((HERE / "labels.json").read_text())["families"]
N = len(KEYS)

_sessions: dict[str, ort.InferenceSession] = {}


def session(choice: str) -> ort.InferenceSession:
    if choice not in _sessions:
        path = hf_hub_download(REPO, MODELS[choice], revision=REVISION)
        _sessions[choice] = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    return _sessions[choice]


def read_mono(path: str) -> np.ndarray:
    """Mono float32 at 48 kHz. soundfile first; ffmpeg for formats it cannot read (m4a, aac, ...)."""
    try:
        info = sf.info(path)
        x, rate = sf.read(path, dtype="float32", always_2d=True, frames=int(info.samplerate * MAX_SECONDS))
        x = x.mean(axis=1)
        return soxr.resample(x, rate, SR).astype(np.float32) if rate != SR else x
    except Exception:
        if not shutil.which("ffmpeg"):
            raise gr.Error("Unsupported audio format / 不支援的音訊格式")
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-t", str(MAX_SECONDS), "-ac", "1",
                              "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
        if out.returncode != 0 or not out.stdout:
            raise gr.Error("Could not decode this file / 無法解碼這個檔案")
        return np.frombuffer(out.stdout, dtype=np.float32).copy()


def loudest_segments(x: np.ndarray, seconds: int, count: int) -> list[tuple[int, np.ndarray]]:
    """(start sample, window) for the loudest non-overlapping windows on a 1 s grid, skipping silence."""
    seg = seconds * SR
    if len(x) <= seg:
        rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
        return [(0, x)] if rms > 0 and 20 * np.log10(rms) > SILENCE_DB else []
    hop = SR
    n = (len(x) - seg) // hop + 1
    power = np.convolve(x.astype(np.float64) ** 2, np.ones(hop), "valid")[::hop]
    per_window = np.array([power[i:i + seconds].sum() for i in range(n)]) / seg
    picked: list[int] = []
    for i in np.argsort(-per_window):
        if len(picked) == count or 10 * np.log10(per_window[i] + 1e-20) < SILENCE_DB:
            break
        if all(abs(int(i) - p) * hop >= seg for p in picked):
            picked.append(int(i))
    return [(p * hop, x[p * hop:p * hop + seg]) for p in sorted(picked)]


def pad(segment: np.ndarray) -> np.ndarray:
    extra = (-len(segment)) % HOP
    if extra:
        segment = np.pad(segment, (0, extra), mode="reflect" if len(segment) > extra else "constant")
    return segment


def name(i: int) -> str:
    return f"{ZH[i]} · {EN[i]}"


def classify(path, top_n, seg_seconds, max_segments, model_choice):
    if not path:
        raise gr.Error("Drop an audio file first / 請先拖放音訊檔")
    t0 = time.perf_counter()
    x = read_mono(path)
    segments = loudest_segments(x, int(seg_seconds), int(max_segments))
    if not segments:
        raise gr.Error("Only silence found / 檔案中只有靜音")
    sess = session(model_choice)
    t1 = time.perf_counter()
    batch = np.stack([pad(s) for _, s in segments])[:, None, :].astype(np.float32)
    seg_emb = sess.run(["audio_embedding"], {"input_values": batch})[0]
    t2 = time.perf_counter()

    logits = PROTOTYPES @ seg_emb.mean(axis=0) * SCALE + BIAS
    p = np.exp(logits - logits.max())
    p /= p.sum()
    sigmoid = 1 / (1 + np.exp(-logits))
    order = np.argsort(-p)[:int(top_n)]

    top = {name(i): float(p[i]) for i in order}
    fam: dict[str, float] = {}
    for i, f in enumerate(FAMILY):
        label = f"{FAMILY_ZH[f]} · {f.replace('_', ' ')}"
        fam[label] = fam.get(label, 0.0) + float(p[i])
    fam = dict(sorted(fam.items(), key=lambda kv: -kv[1]))
    table = [[r + 1, ZH[i], EN[i], FAMILY_ZH[FAMILY[i]], round(100 * float(p[i]), 2),
              round(float(sigmoid[i]), 4), round(float(logits[i]), 3)] for r, i in enumerate(order)]

    per_segment = []
    for (start, s), e in zip(segments, seg_emb):
        lg = PROTOTYPES @ e * SCALE + BIAS
        q = np.exp(lg - lg.max())
        q /= q.sum()
        best = np.argsort(-q)[:3]
        per_segment.append([f"{start / SR:.0f}–{(start + len(s)) / SR:.1f} s"]
                           + [f"{name(i)} ({100 * q[i]:.1f}%)" for i in best])

    summary = (f"**{len(x) / SR:.1f} s** decoded · **{len(segments)}** segment(s) of up to {int(seg_seconds)} s · "
               f"model {model_choice.split(' ')[0]} · inference {t2 - t1:.1f} s (total {t2 - t0:.1f} s) · "
               f"{N} labels")
    return top, fam, table, per_segment, summary


DESCRIPTION = f"""
# 🎻 PE-AV 樂器辨識 · Instrument recognition
拖放一個音訊檔，用 [`{REPO}`](https://huggingface.co/{REPO})（Meta PE-AV small 的音訊編碼器，ONNX）做零樣本樂器辨識。
系統會挑出最大聲的片段送進模型，再和 **{N} 個類別**（{len(FAMILY_ZH)} 個樂器家族）的文字原型比對。單一樂器的錄音（solo / stem）最準；整首混音只會給出大致的組成。

Drop an audio file. The loudest segments go through the ONNX audio encoder and are scored against {N} text prototypes.
Works best on single-instrument recordings (solos, stems).
"""

HELP = """
**分數怎麼看 · How to read the scores**
- **機率 %**：PE-AV logit（`audio · text × scale + bias`）在所有類別上做 softmax，只代表相對排名。
- **sigmoid**：PE-AV 原本的 SigLIP 式分數，每個類別獨立計算；數值普遍很小，比大小即可。
- **家族**：把同一家族的機率加總。
- 文字原型是事先用 PE-AV 文字編碼器算好的，所以無法輸入自訂標籤。標籤和提示詞列在 `labels.json`。
"""

with gr.Blocks(title="PE-AV Instrument Recognition") as demo:
    gr.Markdown(DESCRIPTION)
    with gr.Row():
        with gr.Column(scale=1):
            audio = gr.Audio(sources=["upload", "microphone"], type="filepath",
                             label="音訊檔（拖放或點擊上傳）· Audio file")
            top_n = gr.Slider(5, N, value=30, step=1, label="顯示前 N 名 · Top-N")
            with gr.Accordion("進階設定 · Settings", open=False):
                seg_seconds = gr.Radio([3, 5, 10], value=10, label="片段長度（秒）· Segment length (s)")
                max_segments = gr.Slider(1, 6, value=3, step=1, label="最多片段數 · Max segments")
                model_choice = gr.Dropdown(list(MODELS), value=next(iter(MODELS)), label="模型 · Model",
                                           info="float32 第一次使用時會先下載（約 470 MB）· downloaded on first use")
            run = gr.Button("辨識 · Identify", variant="primary")
            summary = gr.Markdown()
            families = gr.Label(label="樂器家族 · Families", num_top_classes=6)
        with gr.Column(scale=2):
            top = gr.Label(label="Top-N 樂器 · Instruments")
    table = gr.Dataframe(headers=["#", "樂器", "Instrument", "家族", "機率 %", "sigmoid", "logit"],
                         label="排名明細 · Ranking", interactive=False, wrap=True)
    per_segment = gr.Dataframe(headers=["片段 · Segment", "第 1 名", "第 2 名", "第 3 名"],
                               label="各片段前三名 · Top-3 per segment", interactive=False, wrap=True)
    gr.Markdown(HELP)

    inputs = [audio, top_n, seg_seconds, max_segments, model_choice]
    outputs = [top, families, table, per_segment, summary]
    run.click(classify, inputs, outputs)
    audio.upload(classify, inputs, outputs)
    audio.stop_recording(classify, inputs, outputs)

session(next(iter(MODELS)))  # download and load the default model at startup

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch()
