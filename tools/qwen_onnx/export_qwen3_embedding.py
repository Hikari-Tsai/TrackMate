"""Export Qwen/Qwen3-Embedding-0.6B to ONNX with last-token pooling and L2 normalisation.

Inputs  : input_ids [batch, seq] int64, attention_mask [batch, seq] int64
Output  : sentence_embedding [batch, 1024] float32, L2-normalised

The pooled position is the last non-padding token, found from attention_mask, so the
graph works with both left and right padding (the official recipe pads on the left).

Usage: python export_qwen3_embedding.py OUT_DIR
"""
from __future__ import annotations

import pathlib
import sys

import onnx
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"


class PooledEmbedding(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        hidden = self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        positions = torch.arange(input_ids.shape[1], device=input_ids.device).unsqueeze(0)
        last = (positions * attention_mask).argmax(dim=1)  # index of the last attended token
        pooled = hidden[torch.arange(hidden.shape[0], device=hidden.device), last]
        return F.normalize(pooled, p=2, dim=-1)


def main(out_dir: str) -> int:
    out = pathlib.Path(out_dir)
    (out / "onnx").mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID, padding_side="left")
    model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=torch.float32, attn_implementation="eager").eval()
    wrapper = PooledEmbedding(model).eval()

    sample = tok(["Instruct: example\nQuery:kick in", "snare"], padding=True, return_tensors="pt")
    tmp = out / "onnx" / "_tmp" / "model.onnx"
    tmp.parent.mkdir(exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            wrapper, (sample["input_ids"], sample["attention_mask"]), str(tmp),
            input_names=["input_ids", "attention_mask"], output_names=["sentence_embedding"],
            dynamic_axes={"input_ids": {0: "batch", 1: "sequence"},
                          "attention_mask": {0: "batch", 1: "sequence"},
                          "sentence_embedding": {0: "batch"}},
            opset_version=17, do_constant_folding=True, dynamo=False,
        )
    # Re-save with every weight in one external-data file next to the graph (> 2 GB protobuf limit).
    proto = onnx.load(str(tmp), load_external_data=True)
    onnx.save_model(proto, str(out / "onnx" / "model.onnx"), save_as_external_data=True,
                    all_tensors_to_one_file=True, location="model.onnx_data", size_threshold=1024)
    for f in tmp.parent.iterdir():
        f.unlink()
    tmp.parent.rmdir()
    tok.save_pretrained(out)
    model.config.save_pretrained(out)
    print("exported to", out / "onnx" / "model.onnx")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
