# 桌面 App 測試（Flutter）

App 原始碼在 [`app/`](../../app)：介面用 Flutter，拖放和選檔視窗用各平台的原生程式碼（macOS 用 Swift，Windows 用 C++）。

## 自動化測試
| 測試 | 數量 | 內容 |
|---|---|---|
| [`test/app_test.dart`](../../app/test/app_test.dart) | 21 | 兩階段辨識（先文字、後音訊）、Top-5 改選並送回 `/feedback`、手動輸入名稱、搜尋全部樂器、保留原名、大類與顏色連動、百分比顯示、Pro Tools 後綴的保留開關、重複名稱流水號、預覽與套用送出的內容、速度（自動偵測、匯入前選擇、和分軌一起匯入、取消後只重新匯入速度、保留原速度、找不到拍子）、5 張截圖 |
| [`test/errors_test.dart`](../../app/test/errors_test.dart) | 10 | Pro Tools 沒開、沒有 session、沒有回應、套用中斷、檔案遺失、沒有音檔、引擎停止、引擎無法啟動，以及「Try again」的連續流程 |
| [`integration_test/real_flow_test.dart`](../../app/integration_test/real_flow_test.dart) | 1 | 真實的 macOS App、真實的引擎子程序、真實的 Pro Tools |
| [`integration_test/real_tempo_test.dart`](../../app/integration_test/real_tempo_test.dart) | 1 | 同上，自動偵測 85 BPM 分軌的速度，再用 Preview & apply 和分軌一起匯入固定速度與速度圖，兩次都讀回 Pro Tools 確認（[速度偵測報告](tempo-detection.md)） |

**假引擎的資料：** widget 測試使用假的引擎（[`test/fake_engine.dart`](../../app/test/fake_engine.dart)），資料來自真實引擎的輸出（[`test/fixtures/`](../../app/test/fixtures)），可以模擬各種故障。

**截圖測試：** 截圖比對（`golden` 標籤）會受到機器字型影響，所以 CI 不跑，只在本機執行。

## 端到端（真實 App ＋ Pro Tools）
| 步驟 | 時間 |
|---|---|
| App 啟動、引擎就緒 | 6–10 秒 |
| 辨識 10 軌（包含一軌音訊辨識） | 約 16 秒 |
| 從 Top-5 改選一軌 | 約 1 秒 |
| 預覽 | 約 1 秒 |
| 套用到 Pro Tools 並驗證 | 8–9 秒 |
| **合計** | **35–38 秒，10 軌的名稱、資料夾、顏色全部通過** |

**另外確認過的行為：**
- **學習別名：** 改選候選時，送回引擎的別名是去掉歌名後的文字（`synth pad`）；DAW 預設名稱（`Audio 3`）不學。
- **關閉 App：** 引擎會在 1 秒內一起結束，不會留下孤兒程序。
- **打包版：** 解壓後打開，App 會依 CPU 使用內建的引擎（`TrackMate.app/Contents/Resources/engine/arm64` 或 `x86_64`），以及正式的資料夾（`~/Library/Application Support/TrackMate`）。

## 尚未驗證
- **Windows 版：** 會在 CI 上編譯和打包，但還沒有在真實的 Windows 電腦上操作過，拖放和選檔視窗都還沒實測。
- **macOS 原生操作：** 從 Finder 拖放、開檔對話框，只透過共用入口（`addFiles`）測試，原生操作需要手動確認。
- **Pro Tools 異常：** 真的關掉 Pro Tools 或在套用途中強制結束，目前是用模擬的錯誤測試。
