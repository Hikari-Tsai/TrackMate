"""Export the audio branch of Meta PE-AV to ONNX, plus precomputed text prototypes.

Graph:  input_values [batch, 1, samples] float32, 48 kHz mono, samples a multiple of 1920
        -> audio_encoder (DAC encoder, CLS token, transformer) -> CLS -> audio_head
        -> audio_embedding [batch, dim] float32 (raw, NOT normalised)

PE-AV scores audio/text pairs SigLIP-style: logit = audio . text * scale + bias, so the
embedding is exported unnormalised and scale/bias are stored with the prototypes.

Segments are fed without padding: the caller cuts equal-length windows and reflect-pads
each to a multiple of 1920 samples, exactly what PeAudioFeatureExtractor does for a single
clip (its padding mask is then all ones). Leaving the mask out also avoids transformers'
vmap-based mask builder, which the TorchScript exporter cannot trace.

Usage: python export_peav_audio.py MODEL_ID OUT_DIR
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import onnx
import torch

SEGMENT_SAMPLES = 48000 * 10  # 10 s windows, 250 encoder frames


class AudioEmbedding(torch.nn.Module):
    def __init__(self, av_model):
        super().__init__()
        self.encoder = av_model.audio_model.audio_encoder
        self.head = av_model.audio_model.audio_head

    def forward(self, input_values):
        pooled = self.encoder(input_values=input_values).pooler_output
        return self.head(pooled)


def load(model_id: str):
    from transformers import PeAudioVideoModel
    model, info = PeAudioVideoModel.from_pretrained(model_id, ignore_mismatched_sizes=True,
                                                    output_loading_info=True, attn_implementation="eager")
    bad = [k for k in [*info.get("mismatched_keys", []), *info.get("missing_keys", [])]
           if not str(k[0] if isinstance(k, tuple) else k).startswith("video_model.")]
    if bad:
        raise RuntimeError(f"unexpected weight mismatches outside the video branch: {bad}")
    return model.eval()


def main(model_id: str, out_dir: str) -> int:
    out = pathlib.Path(out_dir)
    (out / "onnx").mkdir(parents=True, exist_ok=True)
    model = load(model_id)
    wrapper = AudioEmbedding(model).eval()
    example = torch.randn(2, 1, SEGMENT_SAMPLES) * 0.1
    with torch.no_grad():
        torch.onnx.export(
            wrapper, (example,), str(out / "onnx" / "model.onnx"),
            input_names=["input_values"], output_names=["audio_embedding"],
            dynamic_axes={"input_values": {0: "batch", 2: "samples"}, "audio_embedding": {0: "batch"}},
            opset_version=17, do_constant_folding=True, dynamo=False,
        )
    onnx.checker.check_model(str(out / "onnx" / "model.onnx"))
    scoring = dict(
        logit_scale=float(model.audio_model.text_audio_logit_scale.item()),
        logit_bias=float(model.audio_model.text_audio_logit_bias.item()),
        sample_rate=48000, hop_length=1920, segment_samples=SEGMENT_SAMPLES,
        score="logit = audio_embedding . text_prototype * logit_scale + logit_bias",
    )
    (out / "scoring.json").write_text(json.dumps(scoring, indent=2))
    print("exported", out / "onnx" / "model.onnx", scoring)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
