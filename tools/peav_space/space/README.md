---
title: PE-AV Instrument Recognition
emoji: 🎻
colorFrom: indigo
colorTo: yellow
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
license: apache-2.0
models:
  - aaatmy/pe-av-small-audio-ONNX
  - facebook/pe-av-small
short_description: Zero-shot instrument recognition, PE-AV audio ONNX
---

# PE-AV instrument recognition

Drop an audio file and see which of **169 instruments and sounds** (18 families) it matches,
using [aaatmy/pe-av-small-audio-ONNX](https://huggingface.co/aaatmy/pe-av-small-audio-ONNX),
the audio encoder of Meta's [PE-AV small](https://huggingface.co/facebook/pe-av-small) exported
to ONNX. Runs on CPU with onnxruntime.

**How it works**
1. The file is decoded to 48 kHz mono (the first 10 minutes at most).
2. The loudest non-overlapping segments (default: up to 3 × 10 s) are picked and silence is skipped.
3. Each segment goes through the ONNX audio encoder; the embeddings are averaged.
4. The result is scored against precomputed text prototypes with PE-AV's own logit,
   `audio · text × 2.2057 − 10.1206`, and ranked with a softmax over all labels.

**Labels.** The ONNX model has no text encoder, so each label's text embedding was computed
once with PE-AV's text encoder (mean over 1–3 English prompts × 4 templates). The labels,
Chinese names and prompts are in `labels.json`. Custom labels cannot be entered in this demo.

**Accuracy.** Best on single-instrument recordings (solos, stems). Close relatives (alto vs.
tenor saxophone, violin vs. viola) are often confused; the family view is more reliable. On
full mixes the ranking only shows the rough make-up of the track. For reference, the original
model scored 95.4 % on Medley-solos-DB (8 instruments) in our tests.

Unofficial demo, not affiliated with or endorsed by Meta. Model license: Apache 2.0.
