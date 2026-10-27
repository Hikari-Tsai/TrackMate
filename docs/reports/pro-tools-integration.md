# Pro Tools 整合測試（PTSL）

TrackMate 透過 Avid 的 Pro Tools Scripting Library（PTSL，gRPC，`localhost:31416`）操作 Pro Tools；Python 端使用 [py-ptsl](https://github.com/iluvcapra/py-ptsl)。這份報告記錄在真實 Pro Tools 上逐項驗證的結果，以及實作時必須處理的 PTSL 行為。

- 環境：macOS、Pro Tools 26.4.1、PTSL 版本 2026、py-ptsl 602.0.0
- 腳本：[`tools/ptsl_m0/`](../../tools/ptsl_m0)（逐項探測）、[`engine/stem_engine/protools.py`](../../engine/stem_engine/protools.py)（正式實作）、[`engine/tools/e2e_apply.py`](../../engine/tools/e2e_apply.py)（端到端）
- 所有寫入都在專用的測試 session 中進行。

## 1. 基本操作

| 項目 | 結果 | 耗時 |
|---|---|---|
| 連線（`RegisterConnection`） | 成功 | 第一次 6.8 秒，之後 < 0.1 秒 |
| 建立 session（48 kHz / 24-bit） | 成功 | 2–7 秒 |
| 匯入 6 個檔案到新軌 | 成功；軌名＝檔名去掉副檔名；mono/stereo 檔對應 mono/stereo 軌；中文檔名正常 | 0.8 秒 |
| 匯入 24 個 3 分鐘檔案（933 MB，ConvertAudio） | 成功，指令回傳時檔案已全部寫好 | 3.5 秒 |
| 改名（依目前名稱） | 成功 | < 0.03 秒 |
| 建軌（stereo Aux、mono Audio、Basic Folder、Routing Folder） | 成功 | 0.2 秒 |
| 取得調色盤（`GetColorPalette`） | 69 色 | 0.05 秒 |
| 上色（`SetTrackColor`） | 成功 | 0.02 秒 |
| 刪軌（`DeleteTracks`） | 成功，有 clip 的軌也不跳對話框；軌不存在時正確報錯 | 0.2 秒 |
| Clip List 匯入＋`SpotClipsByID` | 成功；stereo 檔得到 L/R 兩個 clip ID，要一起 spot | — |
| 離線 bounce（`ExportMix`，8 秒） | 成功 | 1.7 秒 |

## 2. 實作必須處理的 PTSL 行為

1. **py-ptsl 602 的 `Engine.import_audio` 不能直接用**：它送出 `import_type=1`，在目前的 proto 中是 `IType_Session`。音訊匯入要自己組 `CId_Import` 並使用 `IType_Audio`（2）。
2. **取樣率不同時要用 ConvertAudio**：CopyAudio 會把 44.1 kHz 檔照原樣複製進 48 kHz session，不轉換也不報錯。TrackMate 一律使用 ConvertAudio（取樣率相同時速度和複製相同）。
3. **改名失敗不會報錯**：改成已存在的名稱、或來源軌不存在時，PTSL 都回報成功但沒有改；只給 `track_id` 也會被忽略，必須帶上 `current_name`。TrackMate 事先讓名稱不重複，改名後再讀回音軌清單驗證。
4. **軌名分大小寫**：`KICK IN` 與 `Kick In` 可以同時存在，避開重名時也以大小寫區分。
5. **一次匯入多個檔案時，新軌依檔名字母排序**；新軌會插在「目前選取的軌」之後（選取資料夾時成為資料夾的第一軌）。TrackMate 逐檔匯入、每次選取前一軌，讓資料夾內的順序符合清單順序。
6. **`SetTrackColor` 的 `color_index` 從 1 開始**；`track_ids` 與 `track_names` 只能給一種，py-ptsl 會送出空清單，所以送出前要移除空欄位。
7. **`ExportMix`、`SaveSessionAs` 的資料夾路徑結尾必須有 `/`**，否則 Pro Tools 會出現斷言錯誤。
8. **`SpotClipsByID` 的位置要用 `location`（TimelineLocation）**，使用 `location_value` 會回 "location" 錯誤。

## 3. 輸出路由

| 項目 | 結果 |
|---|---|
| `CreateSignalPath` 建 bus | PTSL 2026 回 `PT_UnsupportedCommand`（"not yet implemented"） |
| 取得既有路徑 ID | 沒有對應指令；`GetExportMixSourceList` 只回名稱 |
| `SetTrackMainOutputAssignments` | 指令存在，但拿不到合法的路徑 ID，實際無法使用 |
| 放進 Routing Folder 的軌是否改走資料夾 | 否：資料夾靜音前後 bounce 的音檔逐樣本相同 |
| 從範本 session 匯入（Import Session Data） | 各種參數組合皆回 `PT_InvalidParameter` |

**結論**：目前版本不自動路由，改用 **Basic Folder 依大類分組**（建立資料夾 → 選取後匯入 → 資料夾與軌一起上色，已驗證）。每次 Pro Tools 改版時重跑 [`m0b_routing.py`](../../tools/ptsl_m0/m0b_routing.py)，確認是否開始支援建 bus。

## 4. `/apply` 端到端測試

測試 session 預先放了一個 `DRUMS` 資料夾（內含 `Kick In`）和一軌 `Piano`；10 個分軌檔名帶歌名前綴 `MySong_`。

| 項目 | 結果 |
|---|---|
| `/analyze` | 10 軌全部正確；9 軌由字典判斷，名為 `Audio 3` 的小提琴錄音由音訊判斷為 Strings；歌名前綴已去除 |
| `/apply` 預覽（dry run） | 0.3 秒；沿用 `DRUMS`；`Kick In` → `Kick In 2`、`Piano` → `Piano 2`（避開既有軌名） |
| `/apply` | 8.2 秒，10 軌的名稱、資料夾、顏色全部驗證通過；新建 7 個資料夾 |
| 匯入的音檔 | 全部轉為 48 kHz（22.05/44.1 kHz 檔長度不變）；假立體聲與單邊立體聲轉成 mono；真立體聲保留 |

## 5. 例外情況

| 情況 | 引擎回應 | 實測 |
|---|---|---|
| Pro Tools 沒開 | 503 `pro_tools_not_running` | 約 0.2 秒回報，不會卡住 |
| 沒有開啟的 session | 409 `no_session` | — |
| 10 秒內沒有回應 | 504 `pro_tools_not_responding` | 以逾時測試驗證 |
| 套用途中連線中斷 | 503 `pro_tools_lost`（說明可能已建立部分資料夾或軌） | 以模擬的 gRPC 錯誤驗證 |
| 檔案被移走 | 404 `missing_files`（附檔案清單） | — |

相關測試：[`engine/tests/test_errors.py`](../../engine/tests/test_errors.py)、[`app/test/errors_test.dart`](../../app/test/errors_test.dart)。
