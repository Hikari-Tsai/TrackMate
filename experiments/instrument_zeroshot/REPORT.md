# 樂器辨識評測：PE-AV 與 LAION CLAP（NSynth、Medley-solos-DB）

這份評測用來選定 D 層（音訊辨識）的模型。兩個模型都以 zero-shot 方式使用：不重新訓練，直接拿音訊向量和文字描述的向量比對。

- 日期：2026-10-26
- 硬體：Apple Silicon（MPS）
- 腳本：[`eval_instruments.py`](eval_instruments.py)

重現方式：
```bash
uv run --no-project --python 3.12 --with numpy --with soundfile --with soxr --with librosa \
  --with onnxruntime --with "transformers==5.20.2" --with torch --with timm --with pillow \
  python eval_instruments.py --dataset nsynth --models pe-av-small,laion-clap
# 第二份資料集把 --dataset 換成 medley_solos
```
資料集要先下載到 `experiments/datasets/`，取得方式見文末的「資料集」。

## 評測方式
- **文字向量：** 每個類別用 3–4 個同義描述，各套 5 種句型，產生文字向量後取平均，最後選分數最高的類別。
- **兩個模型的計分方式：**
  - **PE-AV small**：音訊向量和文字向量直接內積。這就是模型 logits 的排序依據（logit = 內積 × scale + bias）。
  - **LAION CLAP**（`laion/larger_clap_general`）：cosine 相似度。
- **兩套標籤：**
  - **原生類別**：資料集自己的分類。
  - **10 大類（family10）**：sfx、woodwinds、brass、bass、strings、synth、drums、vocal、guitar、keys，比較接近混音時的大類分法。資料集的類別先對應到這 10 類；沒有對應的類別不計入。

## 指標
| 指標 | 定義 |
|---|---|
| 準確率 | 強制選一個答案時，選對的比例 |
| 平衡準確率 | 每一類的 recall 取平均，避免樣本多的類別主導結果 |
| Macro-F1 | 每一類的 F1 取平均 |
| Recall@3 | 正確類別出現在前 3 名的比例 |

---

## 一、NSynth 測試集（4,096 個 4 秒單音）

**資料：**
- 10 個樂器家族：bass 843、keyboard 766、guitar 652、organ 502、string 306、brass 269、reed 235、mallet 202、flute 180、vocal 141。
- 音色來源：原聲 1,689、電子 1,372、合成 1,035。
- **對應到 10 大類的方式：**
  - flute、reed → woodwinds。
  - keyboard、organ → keys。
  - mallet 沒有對應的大類，不計入，所以剩 3,894 筆。

### 原生 10 類（n = 4,096）
| 模型 | 準確率 | 平衡準確率 | Macro-F1 | Recall@3 | 原聲 | 電子 | 合成 |
|---|---|---|---|---|---|---|---|
| **PE-AV small** | **75.1** | **77.6** | **76.1** | **92.0** | **90.8** | **74.0** | **51.1** |
| LAION CLAP general | 39.7 | 40.7 | 36.1 | 76.3 | 44.4 | 30.7 | 44.0 |

參考：PE-AV 論文 Table 3 中，PE-AV large 在 NSynth 的 zero-shot 結果是 76.8。

### 10 大類（n = 3,894）
| 模型 | 準確率 | 平衡準確率 | Macro-F1 | Recall@3 | 原聲 | 電子 | 合成 |
|---|---|---|---|---|---|---|---|
| **PE-AV small** | **55.7** | **62.6** | **66.7** | **81.0** | **84.5** | **56.5** | 13.2 |
| LAION CLAP general | 33.3 | 36.9 | 34.0 | 63.3 | 40.4 | 15.5 | **46.9** |

**各大類的 recall（%）**
| 大類 | PE-AV small | LAION CLAP |
|---|---|---|
| bass | 25 | 64 |
| brass | 78 | 80 |
| guitar | 67 | 22 |
| keys | 54 | 9 |
| strings | **99** | 49 |
| vocal | 55 | 1 |
| woodwinds | 60 | 33 |

**最常見的錯誤：**
- **PE-AV：** bass → sfx 435、keys → sfx 286、keys → synth 126、keys → vocal 106、bass → drums 105。
- **LAION：** keys → bass 535、guitar → bass 359、keys → brass 247。

---

## 二、Medley-solos-DB 測試集（12,236 段約 3 秒的真實獨奏）

**資料：**
- 8 類，數量不平均，所以要看平衡準確率：長笛 3,167、小提琴 2,900、鋼琴 2,609、女聲 1,142、破音電吉他 955、單簧管 732、小號 406、次中音薩克斯風 325。
- **對應到 10 大類的方式：**
  - 單簧管、長笛、次中音薩克斯風 → woodwinds。
  - 破音電吉他 → guitar；女聲 → vocal；鋼琴 → keys；小號 → brass；小提琴 → strings。

### 原生 8 類
| 模型 | 準確率 | 平衡準確率 | Macro-F1 | Recall@3 |
|---|---|---|---|---|
| PE-AV small | 95.4 | 93.1 | 92.1 | 99.3 |
| LAION CLAP general | **95.5** | **94.8** | **92.4** | **99.5** |

### 10 大類
| 模型 | 準確率 | 平衡準確率 | Macro-F1 | Recall@3 |
|---|---|---|---|---|
| **PE-AV small** | **96.2** | **97.5** | **96.0** | 98.9 |
| LAION CLAP general | 91.6 | 88.7 | 86.6 | **99.0** |

**各類別的 recall（%）**
| 原生類別 | PE-AV small | LAION CLAP |
|---|---|---|
| 單簧管 | 55 | **92** |
| 破音電吉他 | 98 | 98 |
| 女聲 | 99 | 99 |
| 長笛 | **94** | 90 |
| 鋼琴 | **100** | 97 |
| 次中音薩克斯風 | **99** | 85 |
| 小號 | **100** | 98 |
| 小提琴 | 99 | 99 |

**最常見的錯誤：**
- **PE-AV（大類層級）：** woodwinds → keys 101、woodwinds → strings 92、woodwinds → brass 77。
- **LAION（大類層級）：** guitar → strings 177、woodwinds → brass 175、keys → brass 165、guitar → bass 163。

**執行時間**（12,236 段）：PE-AV small 2,946 秒、LAION 535 秒。

---

## 觀察與結論
1. **PE-AV small 在大類層級最穩定。**
   - 真實獨奏片段的準確率 96.2%，平衡準確率 97.5%。
   - LAION 在原生 8 類和 PE-AV 打平，但換成大類後，破音吉他掉到 54%，常被判成 strings 或 bass。
2. **陷阱類別會吸走正常樂器。** NSynth 上 bass 和 keys 大量被判成 sfx 或 drums。所以 D 層的陷阱類別要用具體的描述（例如「a sound effect such as a riser or an impact」），而不是只寫「noise」。
3. **合成音色對兩個模型都很難**（PE-AV 13–51%）。NSynth 的合成 bass、keyboard 本身就很難和合成器分開，這是資料集的特性。
4. **PE-AV 的弱點是木管之間的細分**（單簧管 55%，大多被判成長笛），但這些都屬於 woodwinds，大類層級不受影響。
5. **LAION `larger_clap_music` 的權重有問題：** 不同樂器抽出的音訊向量，相似度最低也有 0.93；在 transformers 5.20 和 4.46、CPU 和 MPS 上結果都一樣。所以改用 `larger_clap_general`。
6. **結論：** D 層採用 PE-AV small。大類準確率已經超過 96%，不需要換成更大的 base 版本。

## 引擎實際路徑的驗證
App 實際使用的是 ONNX 8-bit 版本，會挑出最大聲的片段，再和 16 個類別原型比對。用 Medley-solos 抽 160 段測試（[`engine/tools/eval_audio.py`](../../engine/tools/eval_audio.py)）：
- 大類準確率 96.9%，每段約 1.2 秒。
- 機率門檻設 0.15 時，會回答 98.8% 的片段，答案的準確率 98.1%。

## transformers 5.20 的 PE-AV 相容性問題
1. **影像端權重的形狀和模型不符：** `video_model.video_encoder.embedder.proj.weight` 在權重檔裡是 [768, 1024]，模型初始化時卻是 [768, 2]。這只影響影像端，所以載入時只容許這一項不符，其他權重不符就中止。
2. **`PeAudioVideoModel.get_text_audio_embeds()` 會出錯：** 它呼叫了 `PeAudioModel` 沒有的方法。改用 forward 的實際路徑：取 `text_model` 第一個位置（CLS）的向量，再經過 `audio_model.text_audio_head`。
3. **載入完整模型需要 `timm` 和 `pillow`**，因為影像端用到它們。

## 資料集
| 資料集 | 來源 | 授權 |
|---|---|---|
| NSynth（test split） | Engel et al., 2017，[magenta.tensorflow.org/datasets/nsynth](https://magenta.tensorflow.org/datasets/nsynth) | CC BY 4.0 |
| Medley-solos-DB | Lostanlen & Cella, 2016，[Zenodo record 3464194](https://zenodo.org/records/3464194)，下載檔 MD5 `f5facf398793ef5c1f80c013afdf3e5f` | CC BY 4.0 |

## 限制
- NSynth 是單一音符，不是真實的分軌；其中 25% 是合成音色。
- 沒有調整 prompt，也沒有逐類校準門檻。
- 只測了 PE-AV small，沒有測 base 和 large。
