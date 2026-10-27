# 本機引擎評測

引擎（[`engine/`](../../engine)）負責辨識、立體聲分析、模型下載，以及 Pro Tools 操作。這份報告記錄各層門檻是怎麼決定的，以及引擎實際路徑的評測結果。

## 測試
| 範圍 | 數量 | 檔案 |
|---|---|---|
| 名稱前處理、字典、模糊比對 | 48 | [`test_names.py`](../../engine/tests/test_names.py)、[`test_textmatch.py`](../../engine/tests/test_textmatch.py) |
| 合併邏輯、命名、整合（需要模型時自動跳過） | 7 | [`test_pipeline.py`](../../engine/tests/test_pipeline.py) |
| 模型下載（續傳、校驗失敗） | 3 | [`test_models.py`](../../engine/tests/test_models.py) |
| API（token、Host 檢查、feedback） | 9 | [`test_api.py`](../../engine/tests/test_api.py) |
| `/apply` 規劃（資料夾、重名、覆寫） | 5 | [`test_apply.py`](../../engine/tests/test_apply.py) |
| 例外（Pro Tools 沒開、逾時、中斷、檔案遺失） | 8 | [`test_errors.py`](../../engine/tests/test_errors.py) |
| **合計** | **80** | |

## 文字層（字典 → 模糊比對 → 語意比對）

**測試集：** [`testset_realistic.json`](../../experiments/c_layer_embedding/testset_realistic.json)，177 個手寫、帶雜訊的真實軌名，加上 22 個非樂器名稱（例如歌名、`Song Final v3`）。
**腳本：** [`engine/tools/eval_text.py`](../../engine/tools/eval_text.py)（`--sweep` 可以掃描門檻）。

| 指標 | 結果 |
|---|---|
| Top-1 | **96.6%** |
| Top-5（正確答案在候選清單中） | **98.9%** |
| 自動改名的精確度（信心高或中） | 97.0% |
| 自動改名的召回率 | 92.7% |
| 被自動改名的非樂器名稱 | 0 / 22 |

**語意比對（C 層）門檻：** 掃描結果顯示 `s1 ≥ 0.86` 且第一名和第二名差距 ≥ 0.03 時，精確度從門檻 0.80 時的 93.8% 提高到 97.0%，而且沒有非樂器名稱被自動改名，召回率不變。分數介於 0.62 和 0.86 之間是灰色區，要由音訊層確認大類。

**評測中發現並修正的問題：**
- 單字母縮寫只有在它是整個名稱時才算數，例如 `Song Final v3` 的 `v` 不再被當成 vocal。
- 模糊比對要求兩邊長度相近，`Ai Kotoba` 不再被比成 koto。
- 字典只認出大類詞、名稱裡又有其他字時，改由語意比對細分（`Synthesized Bass` → Synth Bass、`Main Singer` → Lead Vocal）。
- 整批檔案的共同前後綴不會刪掉字典認得的詞（整批 `Tom 1/2/3` 會保留 `Tom`）。

## 音訊層（PE-AV）

**測試：** Medley-solos-DB 測試集，8 種樂器各 20 段，共 160 段。使用引擎實際的處理路徑：ONNX 8-bit、挑最大聲的片段、16 個類別原型。
**腳本：** [`engine/tools/eval_audio.py`](../../engine/tools/eval_audio.py)。

| 指標 | 結果 |
|---|---|
| 大類準確率 | **96.9%** |
| 每段處理時間（CPU） | 約 1.2 秒 |

| 機率門檻 | 回答的比例 | 回答的準確率 |
|---|---|---|
| 0.15（採用） | 98.8% | 98.1% |
| 0.25 | 65.6% | 100% |
| 0.35 | 18.8% | 100% |

一共有 16 個類別，隨機猜的機率約 6%，所以原本設想的 0.35 門檻太高，會擋掉大部分的正確答案。

## Pro Tools 匯出檔名
- **去掉 Pro Tools 加的後綴：** take 和 clip 編號（`_04-01`）、播放清單編號（`.04_09`）、`.dup1`，以及 AudioSuite 處理標記（`-TCEx_01`）。
- **單一字母不當修飾詞：** 依大小寫拆字拆出來的單一字母（`CVox` 拆出的 `C`），不會被當成 L/R/C 這類修飾詞。
- **結果：** `LV2-CVox_04-01` → `Lead Vocal 2`。保留模式下是 `Lead Vocal 2 CVox_04-01`。

## API 實測
| 項目 | 結果 |
|---|---|
| 第一次分析（包含載入模型） | 4.9 秒（7 軌） |
| 之後再分析 | 0.5 秒 |
| 6 個 DAW 預設名稱的真實錄音（只能靠音訊） | 全部判斷到正確大類，共 7.0 秒 |
| 模型下載（1.35 GB，鎖定 commit，邊下載邊算 SHA-256） | 約 2 分鐘，校驗通過 |

## 打包後的引擎
- **打包方式：** 用 PyInstaller 打包成單一資料夾（macOS 約 144 MB，不含模型）。
- **CI 檢查：** CI 會用 [`packaging/smoke_test.py`](../../engine/packaging/smoke_test.py) 確認打包版能啟動並回應 API。
- **本機實測：** 用真實模型跑打包版，四層辨識和立體聲分析都正常（3 軌 22 秒，包含第一次建立語意索引）。
