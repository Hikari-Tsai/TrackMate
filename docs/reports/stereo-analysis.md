# 立體聲／單聲道判斷

分軌檔常常是「假的立體聲」：一個單聲道來源被存成兩聲道，可能偏左或偏右（Pan）、只有一邊有聲音，或是另一邊極性反相。TrackMate 需要判斷每個雙聲道檔是不是其實只有一個來源，如果是，還要在不改變音量和音色的前提下還原成 mono。

- 程式：[`stereo_analysis/stereo_analyzer.py`](../../stereo_analysis/stereo_analyzer.py)
- 測試：[`stereo_analysis/test_stereo_analyzer.py`](../../stereo_analysis/test_stereo_analyzer.py)（27 個）、案例 [`stereo_analysis/cases.py`](../../stereo_analysis/cases.py)

## 方法：共變異數的 rank-1 殘差

單一 mono 來源放進立體聲時，不論 Pan 位置、Pan law 或極性為何，都滿足 `L(t) = a·s(t)`、`R(t) = b·s(t)`，也就是 (L, R) 的樣本點會落在一條通過原點的直線上。

所以 TrackMate 不直接比較 L 和 R（一旦有 Pan 就會失準），而是看 2×2 共變異數矩陣有多接近 rank 1：

```
residual_db = 10 · log10(λmin / λmax)
```

- **完全相同或有 Pan 的 mono：** 殘差非常低（−60 dB 以下）。
- **極性反相的 mono：** 一樣很低（直線斜率變成負的）。
- **真立體聲、殘響、XY 收音：** 殘差高（通常高於 −20 dB）。

另外還做了這些處理：
- **Pan 和極性：** 主特徵向量直接給出 Pan 位置和極性；把訊號投影到主特徵向量上，就得到不會抵銷、並保留最大聲道音量的 mono 版本。
- **只用有聲音的片段：** 所有統計只計算「有聲音」的音框（高於絕對門檻，且不低於最大聲音框太多），所以長時間的靜音、淡入淡出、dither 雜訊都不會干擾判斷。
- **偵測延遲的 mono：** 用交叉相關找出一邊比另一邊晚幾毫秒的情況（Haas 效果、間距麥克風）。

## 判斷結果與建議動作

| 類型 | 意思 | 建議動作 |
|---|---|---|
| `mono_file` | 本來就是單聲道 | 保留 |
| `fake_stereo` | 單一來源（含 Pan、極性反相） | 投影成 mono |
| `hard_left` / `hard_right` | 另一邊沒有聲音或低 30 dB 以上 | 取有聲音的那一邊 |
| `delayed_mono` | 同一來源有時間差 | 保留（避免梳狀濾波） |
| `true_stereo` | 真的立體聲 | 保留 |
| `silent` | 沒有聲音 | 保留，標記 |
| `multichannel` | 超過兩聲道 | 保留 |

主要參數：
- 音框 0.1 秒。
- 絕對門檻 −70 dBFS，相對範圍 50 dB。
- 單邊判定 30 dB。
- mono 殘差門檻 −30 dB，容許 MP3/AAC 這類有損編碼。

## 測試案例（全部通過）

| 案例 | 預期 |
|---|---|
| 置中 mono（L = R） | fake_stereo |
| mono Pan 左 30%、右 80% | fake_stereo |
| 只有左聲道（右邊數位靜音）／右邊有 −65 dBFS 雜訊 | hard_left |
| 只有右聲道（左邊 −46 dB 串音） | hard_right |
| 極性反相（R = −L） | fake_stereo |
| 70% 靜音的稀疏 mono 分軌 | fake_stereo |
| mono 加 −35 dB 聲道雜訊（模擬有損編碼） | fake_stereo |
| 左聲道有 DC 偏移的 mono | fake_stereo |
| 兩個不同來源 | true_stereo |
| mono 加寬廣的立體聲殘響 | true_stereo |
| 右邊延遲 12 ms（Haas） | delayed_mono |
| 前 70% mono、後 30% 真立體聲 | true_stereo |

另外也測了單聲道檔、靜音檔，以及 `write_downmix` 輸出的音量與相位。

## 在 TrackMate 中的使用
- **分析：** `/analyze` 會回傳每個檔案的類型和建議動作。前端依建議預設勾選「To mono」，使用者可以改。
- **轉換：** `/apply` 匯入前，用 `write_downmix` 寫出 mono 暫存檔，匯入後刪除。
