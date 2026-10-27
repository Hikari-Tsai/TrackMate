# 模型匯出與量化（ONNX）

TrackMate 在本機用 onnxruntime 執行兩個模型。兩個模型都是從官方權重自行匯出成 ONNX、逐一和 PyTorch 比對驗證之後，才上傳到 Hugging Face；App 第一次啟動時會下載。

| 用途 | 原始模型 | ONNX repo | App 使用的檔案 | 大小 |
|---|---|---|---|---|
| 語意比對（C 層） | [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | [aaatmy/Qwen3-Embedding-0.6B-ONNX](https://huggingface.co/aaatmy/Qwen3-Embedding-0.6B-ONNX) | `tokenizer.json`、`onnx/model_q8_int8compute.onnx` | 約 1.13 GB |
| 音訊（D 層） | [facebook/pe-av-small](https://huggingface.co/facebook/pe-av-small) | [aaatmy/pe-av-small-audio-ONNX](https://huggingface.co/aaatmy/pe-av-small-audio-ONNX) | `onnx/model_q8.onnx`、`scoring.json` | 222 MB |

版本鎖定在特定 commit，每個檔案的 SHA-256 都寫在 [`model_manifest.json`](../../engine/stem_engine/data/model_manifest.json) 中。

## Qwen3-Embedding-0.6B
- **匯出：** [`tools/qwen_onnx/export_qwen3_embedding.py`](../../tools/qwen_onnx/export_qwen3_embedding.py)。把 last-token pooling 和 L2 正規化包進計算圖，用 TorchScript exporter 匯出（opset 17）。需要 transformers 4.51.3 和 torch 2.6.0，因為新版 transformers 用 `vmap` 建 attention mask，exporter 無法追蹤。
- **量化：** [`tools/qwen_onnx/quantize_int8.py`](../../tools/qwen_onnx/quantize_int8.py)。使用 onnxruntime `MatMulNBitsQuantizer`：8-bit、block 32、對稱量化、只量化 MatMul。

**和官方輸出比對**（2,280 筆中、英、日文樂器名稱與軌名）：
| 檔案 | 最低 cosine | 平均 cosine |
|---|---|---|
| float32 | 0.99944 | 0.99981 |
| q8 | 0.99814 | 0.99929 |
| q8 int8compute（App 預設） | 0.99618 | 0.99863 |

- **辨識準確率：** 三個版本在 C 層測試集上的 Recall@1，和 PyTorch 原版最多差 1.1 個百分點。
- **CPU 延遲：** 單筆查詢時，float32 約 112 ms，q8 int8compute 約 54 ms。
- **不採用的版本：** `quantize_dynamic` 一般 int8 量化（包含 Gather）會毀掉向量，平均 cosine 只有 0.77。
- **驗證腳本：** [`tools/qwen_onnx/verify_parity.py`](../../tools/qwen_onnx/verify_parity.py)。

## PE-AV small（只有音訊端）
- **匯出：** [`tools/peav_onnx/export_peav_audio.py`](../../tools/peav_onnx/export_peav_audio.py)。只匯出音訊編碼器（DAC encoder、CLS、transformer）加上 `audio_head`，約 1.17 億參數，跳過文字端和影像端。輸入是 48 kHz mono，長度補到 1920 的倍數。
- **計分：** `logit = audio · text × 2.2057 − 10.1206`，用 SigLIP 式的 sigmoid logit。
- **文字端：** 不打包進 App。16 個類別原型事先用 PyTorch 算好，存成 [`peav_prototypes.npz`](../../engine/stem_engine/data/peav_prototypes.npz)。產生腳本是 [`engine/tools/build_peav_prototypes.py`](../../engine/tools/build_peav_prototypes.py)。

**和 PyTorch 比對**（[`tools/peav_onnx/verify_peav_parity.py`](../../tools/peav_onnx/verify_peav_parity.py)，3、4、10、30 秒片段）：
| 檔案 | 片段數 | 最低 cosine | Top-1 一致 |
|---|---|---|---|
| float32 | 100 | 1.000000 | 100% |
| q8（App 使用） | 250 | 0.99944 | 3/10/30 秒片段 100%；4 秒 NSynth 單音 97% |

- **不採用的版本：** `accuracy_level=4`（在 MatMulNBits 裡用 int8 運算），最低 cosine 只有 0.9966。
- **CPU 延遲：** 每 10 秒片段約 2.8 秒。8-bit 版沒有比較快，因為時間主要花在沒有量化的卷積層。
- **CoreML：** CoreML execution provider 需要固定輸入長度；CPU 加神經網路引擎也只快約 18%，所以沒有採用。

## 首次下載
- **大小：** 合計約 1.35 GB。
- **完整性：** 引擎的下載器支援續傳，邊下載邊計算 SHA-256，吻合後才把檔案換成正式檔名。
- **未下載完成時：** 字典和模糊比對兩層仍然可以使用。
