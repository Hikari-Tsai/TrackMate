# 研究與測試報告

| 報告 | 內容 |
|---|---|
| [語意比對模型比較](../../experiments/c_layer_embedding/REPORT.md) | multilingual-e5-small、Qwen3-Embedding-0.6B、bge-m3 在軌名 → 樂器上的 Recall@1/3/5，含中日文和跨語言測試 |
| [樂器辨識評測](../../experiments/instrument_zeroshot/REPORT.md) | PE-AV small 與 LAION CLAP 在 NSynth、Medley-solos-DB 上的 zero-shot 結果，D 層模型選擇 |
| [模型匯出與量化](model-export.md) | Qwen3-Embedding、PE-AV 音訊端的 ONNX 匯出、量化與一致性驗證 |
| [立體聲／單聲道判斷](stereo-analysis.md) | rank-1 共變異數殘差演算法與 27 個測試 |
| [本機引擎評測](engine-evaluation.md) | 各層門檻的決定方式、文字層與音訊層的實際表現、打包驗證 |
| [Pro Tools 整合測試](pro-tools-integration.md) | PTSL 每項操作的實測、必須處理的行為、路由的限制、`/apply` 端到端、例外情況 |
| [桌面 App 測試](app-testing.md) | widget 測試、例外測試、真實 App 端到端 |

原始評測數據：
- [`experiments/c_layer_embedding/results/summary.json`](../../experiments/c_layer_embedding/results/summary.json)
- [`experiments/instrument_zeroshot/results/`](../../experiments/instrument_zeroshot/results)
