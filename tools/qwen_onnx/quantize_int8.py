"""Weight quantisation variants of the exported Qwen3-Embedding ONNX model.

  dynamic      int8 per-channel dynamic quantisation of MatMul + Gather (first attempt;
               too lossy for this model, kept for comparison)
  matmul_only  same, but the token-embedding Gather stays float32
  block8       weight-only block-wise int8 MatMul (MatMulNBits, block 32); embeddings stay float32
               (quantising the Gather forces an opset-21 upgrade that breaks ReduceMean)
  block4       weight-only block-wise int4 (block 32)
  block8acc4   block8 with accuracy_level=4 (int8 compute in MatMulNBits, faster on CPU)

Usage: python quantize_int8.py MODE SRC_ONNX DST_ONNX
"""
from __future__ import annotations

import sys

import onnx


def main(mode: str, src: str, dst: str) -> int:
    if mode in ("dynamic", "matmul_only"):
        from onnxruntime.quantization import QuantType, quantize_dynamic
        quantize_dynamic(model_input=src, model_output=dst, weight_type=QuantType.QInt8, per_channel=True,
                         op_types_to_quantize=["MatMul", "Gather"] if mode == "dynamic" else ["MatMul"],
                         use_external_data_format=mode == "matmul_only")
    elif mode in ("block8", "block4", "block8acc4"):
        from onnxruntime.quantization.matmul_nbits_quantizer import (DefaultWeightOnlyQuantConfig,
                                                                     MatMulNBitsQuantizer)
        bits = 4 if mode == "block4" else 8
        level = 4 if mode == "block8acc4" else None
        cfg = DefaultWeightOnlyQuantConfig(block_size=32, is_symmetric=True, bits=bits, accuracy_level=level,
                                           op_types_to_quantize=("MatMul",),
                                           quant_axes=(("MatMul", 0),))
        q = MatMulNBitsQuantizer(onnx.load(src), bits=bits, block_size=32, is_symmetric=True,
                                 accuracy_level=level, algo_config=cfg,
                                 op_types_to_quantize=("MatMul",),
                                 quant_axes=(("MatMul", 0),))
        q.process()
        q.model.save_model_to_file(dst, use_external_data_format=False)
    else:
        raise ValueError(mode)
    print("wrote", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
