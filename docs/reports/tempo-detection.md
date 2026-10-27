# 速度偵測（BPM）與匯入 Pro Tools

TrackMate 用 [Beat This!](https://github.com/CPJKU/beat_this)（Foscarin、Schlüter、Widmer，ISMIR 2024，`final0`）找出鼓組分軌的每一拍和每小節第一拍，換算成固定速度或速度圖，寫成只含速度的 MIDI 檔，再透過 PTSL 匯入 Pro Tools 並確認結果。

- 程式：[`engine/stem_engine/tempo.py`](../../engine/stem_engine/tempo.py)、[`protools.py`](../../engine/stem_engine/protools.py)、[`app/lib/ui/tempo_dialog.dart`](../../app/lib/ui/tempo_dialog.dart)
- 模型：[aaatmy/beat-this-onnx](https://huggingface.co/aaatmy/beat-this-onnx)（FP32 ONNX，82 MB，鎖定 commit、SHA-256 校驗）
- 環境：macOS（Apple Silicon）、Pro Tools 26.4.1、PTSL 2026

## 1. ONNX 版和 PyTorch 原版一致

前處理（22.05 kHz、n_fft 1024、hop 441、Slaney mel 128 維、`log1p(1000·x)`）、分段（每段 1500 格、前後各丟 6 格、重疊處以前一段為準）和峰值挑選（±3 格最大值、相鄰合併）都照原版實作，用 numpy 寫成，不需要 PyTorch。

| 比對（`choice.ogg`，25 秒，鼓＋貝斯） | 結果 |
|---|---|
| 拍子數 | 29（原版 29） |
| 與原版拍子的差距 | 全部在 25 ms 內，最大 9.7 ms（多出的差距來自下面的次格定位） |
| 小節第一拍 | 8（原版 8） |
| BPM | 68.01（原版 68.007） |

**音量不能拉高：** 一開始把混音正規化到滿刻度，結果多了 8 個假的拍子（37 拍）。Beat This! 的頻譜是 `log1p(1000·x)`，和音量有關，所以現在保留原本的音量，只有加總後會破音時才降低。

**次格定位：** 模型每秒 50 格，原版的拍子時間是 20 ms 的倍數。在 120 BPM 時，相鄰兩拍的間隔會在 115–125 BPM 之間跳動。TrackMate 用峰值和左右兩格擬合拋物線，把拍子定位到格與格之間。

## 2. 拍子的整理

真實分軌常見兩種情況，會讓「每兩拍之間就是一個四分音符」不成立：

1. **某段被聽成倍速：** 前奏只有 hi-hat 或琶音時，模型可能抓到八分音符。
2. **分軌停下來：** 鼓組在前奏或間奏沒有聲音，中間缺了拍子。

TrackMate 以拍子間隔的中位數為準：離前一拍不到 0.7 個間隔的拍子去掉，間隔超過一拍的地方依比例補回。因此同一首歌裡超過約 30% 的速度變化不會被跟上（記在已知限制）。

## 3. 準確度

| 素材 | 已知速度 | 來源分軌 | 結果 | 建議 |
|---|---|---|---|---|
| `choice.ogg` | 68（原版輸出） | 1 | 68.01 BPM，網格誤差 11 ms，4/4 | 固定 |
| 商用 loop 組成的分軌（7 軌，19 秒） | 100 | 1 軌鼓 | 99.91 → 100 BPM，網格誤差 21 ms，4/4 | 固定 |
| 原創曲多軌（REAPER 專案設定 85 BPM，271 秒） | 85 | 9 軌鼓 | 整理前：85.79、判為變速（前奏 13 秒被聽成倍速，鼓從 26 秒才進來）<br>整理後：**85.00 BPM**，網格誤差 16 ms | 固定 |
| 同一組鼓分 4 段加速（×0.9、×1.0、×1.1、×1.2） | 76.5 / 85 / 93.5 / 102 | 5 軌鼓 | 速度圖各段中位數 76.48 / 85.04 / 93.64 / 101.96 | 變速 |

**固定或變速：** 對所有拍子擬合一條直線，每一拍都在 30 ms 內時建議固定速度。85 BPM 的歌整首 324 拍，最大偏差 16 ms；加速的版本偏差 4.9 秒，判為變速。

**速度：** 271 秒、9 軌鼓的偵測約 12 秒（讀檔和重新取樣佔大半），App 裡 60 秒、4 軌約 5 秒。

## 4. 匯入 Pro Tools

PTSL 2026 沒有設定速度的指令（`libPTSL.dylib` 的 150 個指令裡也沒有），也不能直接匯入 MIDI。實測找到的做法：

| 測試 | 結果 |
|---|---|
| 用 `Import`（`IType_Audio`）匯入 `.mid` | Pro Tools 跳出 **MIDI Import Options**，預設勾選 *Import tempo map from MIDI File*、位置 *Session Start*；按 OK 後指令才回傳 |
| 只含速度的 MIDI | 不會多出空的 MIDI 軌；速度尺和拍號尺換成檔案裡的內容 |
| 按 Cancel | PTSL 一樣回報成功，**分不出來** |
| `Import`（`IType_Session`，`tempo_meter_map`） | 只能從 `.ptx` 匯入，無法產生指定速度的 session 檔，不採用 |

**確認速度有沒有改：** 把時間軸選取移到某個 sample 位置，再用 `GetTimelineSelection` 以 Bars|Beats 讀回（讀完把選取還原）。例如 97 BPM 時，第 60 秒讀到 `25| 2| 000`（97 個四分音符）。TrackMate 在最後一拍的位置讀回，和自己的速度圖算出的位置比對（容許 0.05 拍）。

| `/tempo/apply` 實測（85 BPM 分軌） | 讀回位置 | 預期 | `applied` |
|---|---|---|---|
| 固定 85 BPM，按 OK | `91| 1| 027`（360.028 拍） | 360.028 | true |
| 速度圖（88 個速度點），按 OK | `91| 1| 634`（360.660 拍） | 360.660 | true |
| 固定 120 BPM，按 Cancel | `91| 1| 634`（沿用前一次） | 508.275 | **false** |

App 依 `applied` 顯示「Pro Tools tempo is now 85 BPM（在第 91 小節確認）」，或提醒對話框被取消、要再匯入一次。

## 5. 測試

| 測試 | 內容 |
|---|---|
| [`engine/tests/test_tempo.py`](../../engine/tests/test_tempo.py)（13） | 來源分軌的選擇、次格定位、倍速與缺拍的整理、固定／變速判斷、MIDI 內容（用獨立的解析器確認每條小節線落在偵測到的時間，誤差 < 2 ms）、半速／倍速、Bars|Beats 解析、API（模型未就緒、只存 MIDI、Pro Tools 沒開、驗證結果），以及用真實模型偵測 112 BPM 的合成鼓組（中間有一小節靜音） |
| [`app/test/app_test.dart`](../../app/test/app_test.dart)（6） | 加入分軌後自動偵測並顯示在右上角（只顯示、不能點）、清單改變後重新偵測；Preview & apply 先選速度（半速／倍速、固定／速度圖）再預覽，分軌匯入後才匯入速度；在 Pro Tools 按取消後，結果視窗可以只重新匯入速度；保留原速度或在速度步驟取消；找不到拍子時標題列顯示「No BPM found」、可以重新偵測或不設定速度繼續；速度步驟截圖 |
| [`app/integration_test/real_tempo_test.dart`](../../app/integration_test/real_tempo_test.dart) | 真實 App、引擎和 Pro Tools（85 BPM 分軌的 60 秒片段，鼓 4 軌＋貝斯） |

### App 的流程

- **自動偵測：** 分軌辨識完後，在背景偵測速度，顯示在右上角（只顯示，不是按鈕）。新增或移除分軌後會重新偵測；改了大類，到匯入時才重新偵測。
- **匯入前一定要選：** 按右下角的 Preview & apply 後，先跳出速度視窗：固定速度、速度圖或保留 session 原本的速度，以及半速／倍速。之後才是資料夾和名稱的預覽。
- **和分軌一起匯入：** 先匯入分軌，再匯入速度；結果視窗同時列出分軌驗證和速度確認。速度沒有設定成功時（例如在 Pro Tools 按了取消），可以按 **Import tempo again** 只重新匯入速度，不會重複匯入分軌。

真實 App 的結果：

| 步驟 | 時間 | 結果 |
|---|---|---|
| 辨識 5 軌 | 1.4 秒 | 鼓 4 軌、貝斯 1 軌 |
| 自動偵測速度 | 5.7 秒 | 85.0 BPM，建議固定，顯示在右上角 |
| Preview & apply：固定 85 BPM（5 軌＋速度） | 約 11 秒（含按 OK） | 5 軌名稱、資料夾、顏色通過；讀回 `22| 1| 340`，與預期相同 |
| Preview & apply：速度圖 22 點（5 軌＋速度） | 約 11 秒 | 5 軌通過；讀回 `22| 1| 343`，與預期相同 |

測試時由腳本代替使用者按 MIDI Import Options 的 OK（System Events）。TrackMate 本身不模擬點擊，對話框一律由使用者確認。

## 6. 尚未驗證

- **Windows 版 Pro Tools：** MIDI Import Options 的行為只在 macOS 上確認過。
- **拍號變化與自由速度：** 混合拍號（例如 7/8）和沒有固定拍子的段落（rubato）還沒有用真實歌曲測過；x/4 以外的拍號會寫成 x/4。
- **半速／倍速：** 模型聽成半速或倍速時由使用者選擇，沒有自動判斷。
