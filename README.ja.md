<p align="center"><img src="docs/images/trackmate_icon.png" width="128" alt="TrackMate icon"></p>

<p align="center"><a href="README.md">English</a> | <a href="README.zh-TW.md">繁體中文</a> | <b>日本語</b></p>

<p align="center">
  <a href="https://github.com/Hikari-Tsai/TrackMate/releases/latest/download/TrackMate-macos-universal.dmg"><img src="https://img.shields.io/badge/Download-macOS%20Universal-5B5BD6?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTIxIDE1djRhMiAyIDAgMCAxLTIgMkg1YTIgMiAwIDAgMS0yLTJ2LTQiLz48cG9seWxpbmUgcG9pbnRzPSI3IDEwIDEyIDE1IDE3IDEwIi8+PGxpbmUgeDE9IjEyIiB4Mj0iMTIiIHkxPSIxNSIgeTI9IjMiLz48L3N2Zz4K" alt="macOS 版（ユニバーサル）をダウンロード"></a>
  <a href="https://github.com/Hikari-Tsai/TrackMate/releases/latest/download/TrackMate-windows-x64.zip"><img src="https://img.shields.io/badge/Download-Windows%20x64-5B5BD6?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTIxIDE1djRhMiAyIDAgMCAxLTIgMkg1YTIgMiAwIDAgMS0yLTJ2LTQiLz48cG9seWxpbmUgcG9pbnRzPSI3IDEwIDEyIDE1IDE3IDEwIi8+PGxpbmUgeDE9IjEyIiB4Mj0iMTIiIHkxPSIxNSIgeTI9IjMiLz48L3N2Zz4K" alt="Windows x64 版をダウンロード"></a>
  <br>
  <a href="https://github.com/Hikari-Tsai/TrackMate/releases/latest"><img src="https://img.shields.io/github/v/release/Hikari-Tsai/TrackMate?label=latest%20release" alt="最新リリース"></a>
  <a href="https://github.com/Hikari-Tsai/TrackMate/actions/workflows/ci.yml"><img src="https://github.com/Hikari-Tsai/TrackMate/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# TrackMate

> このドキュメントは英語版 README の翻訳です。内容は[英語版](README.md)が優先されます。

TrackMate は、Pro Tools でミックスを始める前のいちばん面倒な整理作業を引き受けます。ステムのファイル名はばらばらで、誤字や略語だらけ。本来はモノラルなのにステレオで書き出されたトラックも混ざっています。

TrackMate は各ステムの楽器を認識し、標準のトラック名・カテゴリ・カラーを提案して、モノラルに戻すべきかどうかも判定します。ドラムのステムから曲のテンポ（BPM）も検出します。確認したらワンクリックで Pro Tools に取り込み、カテゴリごとのフォルダ作成、インポート、リネーム、カラー設定、テンポ設定まで行います。

認識はルールと AI モデルの組み合わせです。
- **ルール：** よく使われるトラック名の辞書とスペル補正。
- **名前を読む：** 多言語対応のテキスト埋め込みモデル Qwen3-Embedding-0.6B が、初めて見るトラック名も理解します。
- **音を聴く：** Meta が事前学習した音声–テキストモデル PE-AV（CLAP と同系統。音声エンコーダーのみを ONNX に変換）が、名前から判断できないトラックを担当します。
- **拍を取る：** ビートトラッキングモデル Beat This!（CPJKU、ISMIR 2024、ONNX に変換）が、ドラムとパーカッションのステムから各拍と小節の頭（ダウンビート）を検出します。

実際のトラック名を使ったテストでは、Top-1 正解率 96.6 %、正解が上位 5 件に入る割合は 98.9 % でした。

Pro Tools の操作は、AppleScript でマウスクリックを再現する方式ではなく、Avid 公式の Pro Tools Scripting Library（PTSL）で行います。画面のレイアウト変更の影響を受けにくく、今後のバージョンでも動作し続けやすい方式です。

![TrackMate のトラック一覧](docs/images/track_list.png)

- **4 段階の認識：** 既知のトラック名 → スペル補正 → AI による名前の読み取り → 音の聴き取り。中国語・英語・日本語の名前に対応し、名前から判断できないトラック（例：`Audio 3`）は音声で認識します。
- **迷うところはユーザーが決める：** 各トラックに Top-1 の結果と信頼度を表示します。メニューには上位 5 件が並び、名前の手入力、全楽器の検索、元の名前の維持、カテゴリやカラーの変更もできます。
- **ステレオ解析：** 疑似ステレオ、片側だけのステレオ、逆相、ディレイを検出し、必要に応じてモノラルに変換します。
- **BPM 検出：** 右上に BPM をすぐ表示します。固定テンポ（平均値を四捨五入）か、小節ごとに変わるテンポマップかを選ぶと、TrackMate が Pro Tools に取り込み、セッションのテンポが変わったことを確認します。テンポは MIDI ファイルとしても保存されます。
- **Pro Tools 連携：** PTSL 経由で操作します。名前の重複は自動で避け、適用後は各トラックの名前・フォルダ・カラーを検証します。
- **すべてローカルで動作：** モデルは初回起動時にダウンロードし、その後はネットワーク不要です。

---

## 目次
- [ダウンロードとインストール](#ダウンロードとインストール)
- [使い方](#使い方)
- [アルゴリズム](#アルゴリズム)
- [システム構成](#システム構成)
- [ソースからのビルドとテスト](#ソースからのビルドとテスト)
- [リポジトリ構成](#リポジトリ構成)
- [研究とテストのレポート](#研究とテストのレポート)
- [CI/CD](#cicd)
- [既知の制限](#既知の制限)
- [謝辞](#謝辞)
- [ライセンス](#ライセンス)

---

## ダウンロードとインストール
<sub>[English](README.md#download-and-install)</sub>

### 動作環境
| 項目 | 要件 |
|---|---|
| macOS | macOS 14（Sonoma）以降。Apple Silicon と Intel の両方に対応（1 つのユニバーサルアプリ） |
| Windows | Windows 10/11 x64（CI でビルド済み。実機での検証はまだです。[既知の制限](#既知の制限)を参照） |
| Pro Tools | PTSL 対応バージョン（2023.3 以降）。Pro Tools 26.4.1 で検証。カラー設定には `SetTrackColor` に対応した PTSL が必要 |
| ディスク容量 | macOS アプリ約 340 MB（両方の CPU 用エンジンを同梱）、Windows 約 150 MB。初回起動時に約 1.43 GB のモデルをダウンロード |

### インストール
1. 上部のボタンから最新版をダウンロードするか、[Releases](https://github.com/Hikari-Tsai/TrackMate/releases) でバージョンを選びます。
   - macOS：[`TrackMate-macos-universal.dmg`](https://github.com/Hikari-Tsai/TrackMate/releases/latest/download/TrackMate-macos-universal.dmg)（または `.zip`）。Apple Silicon と Intel の Mac で使えます
   - Windows：[`TrackMate-windows-x64.zip`](https://github.com/Hikari-Tsai/TrackMate/releases/latest/download/TrackMate-windows-x64.zip)
2. **macOS：** `TrackMate.app` を「アプリケーション」フォルダにドラッグします。現在のビルドは Apple の公証を受けていないため、初回はアプリを右クリックして「開く」を選ぶか、ターミナルで次を実行してください。
   ```bash
   xattr -dr com.apple.quarantine /Applications/TrackMate.app
   ```
3. **Windows：** 解凍して `TrackMate.exe` を起動します。SmartScreen の警告が出たら「詳細情報」→「実行」を選びます。
4. **初回起動：** アプリがバックグラウンドでモデルをダウンロードし、ヘッダーに進捗を表示します。ダウンロード完了前でも、既知のトラック名とスペル補正による認識は使えます。モデルと設定の保存先：
   - macOS：`~/Library/Application Support/TrackMate`
   - Windows：`%APPDATA%\TrackMate`

## 使い方
<sub>[English](README.md#usage)</sub>

![空の状態](docs/images/empty_state.png)

1. **Pro Tools と取り込み先のセッションを開きます。** タイトルの下に、セッション名とサンプルレートが表示されます。
2. **ステムを追加：** オーディオファイルやフォルダをウィンドウにドラッグするか、**Add audio files** を押します。対応形式：WAV、AIFF、MP3、FLAC、M4A、OGG、CAF。
3. **結果を確認：**
   - まず名前による結果が表示され、名前から判断できないトラックは続けて音で認識されます（*Listening…* と表示）。
   - 信頼度の低いトラックはオレンジで強調され、ヘッダーに要確認の件数が表示されます。信頼度の列にマウスを乗せると、どの方法で認識したかがわかります。
4. **修正：**
   - **新しい名前のメニュー（上位 5 件）：** 別の候補を選ぶか、*Type a name…*（手入力）、*Search all instruments…*（全楽器を検索）、*Keep original name*（元の名前のまま）を選びます。名前欄を直接編集することもできます。
   - **Category：** カテゴリを変えると、カラーもそのカテゴリの既定色に変わります。
   - **カラー見本：** Pro Tools の 69 色パレットから選べます。
   - **To mono：** ステレオ解析の推奨に従って最初からチェックされています。変更も可能です。
   - 上位 5 件から選び直した楽器は記憶され、次に同じ名前が来たときは正しく認識されます。
5. **Keep unrecognised words（既定はオフ）：** オフのときは、認識できなかった語と Pro Tools のサフィックス（`_04-01`、`-TCEx_01` など）を削除します。オンにすると残します。名前が重複した場合は連番が付きます（例：`Lead Vocal 1`、`Lead Vocal 2`）。
6. **Preview & apply を押す：** 作成されるフォルダ、各トラックの最終的な名前、モノラル変換の有無をまずプレビューで確認します。確定するまで Pro Tools には何も書き込みません。完了後は、各トラックに検証結果が表示されます。
7. **テンポ（任意）：** 右上の **Detect BPM** を押します。TrackMate はドラムとパーカッションのステム（ない場合はベース、ギター、キーボード、シンセ）を聴いて BPM をすぐ表示し、テンポの設定画面を開きます。
   - **Import as（取り込み方法）：** *Constant tempo* はセッション全体を 1 つの BPM にします。平均値を四捨五入した値で、− と + で調整できます。*Tempo map (variable)* は小節ごとにテンポを設定し、すべての小節線をステムで聴こえた小節の頭に合わせます。すべての拍が 1 本の直線グリッドから 30 ms 以内なら、固定テンポを提案します。
   - **Beat（拍）：** 半分または倍のテンポで検出された場合は、*½× half time* か *2× double time* を選びます。
   - **Import to Pro Tools：** Pro Tools に *MIDI Import Options* ダイアログが表示されます。*Import tempo map from MIDI File* をオンのまま **OK** を押してください。TrackMate はセッションを読み直して新しいテンポを確認し、変わらなかった場合（キャンセルしたときなど）はそれを知らせます。
   - **Save MIDI：** テンポファイル（`TrackMate Tempo 85 BPM.mid` または `TrackMate Tempo Map (avg 85 BPM).mid`）をステムと同じ場所に保存します。ほかの DAW でも使えます。
   - *Also import the tempo with Preview & apply*（既定でオン）がオンなら、手順 6 でトラックの取り込み後にテンポも設定します。ステムを追加・削除すると結果は消えるので、もう一度検出してください。

![テンポの設定](docs/images/tempo_dialog.png)

![Category メニュー](docs/images/category_menu.png)

問題が起きると、アプリが状況と対処方法を表示します。

![Pro Tools が起動していないときの通知](docs/images/alert_pro_tools.png)

| 状況 | 通知 | 対処 |
|---|---|---|
| Pro Tools が起動していない | Pro Tools is not running | Pro Tools を起動して *Try again* |
| セッションが開かれていない | No session is open in Pro Tools | セッションを開いて *Try again* |
| Pro Tools がビジー、またはダイアログ表示中 | Pro Tools is not responding | ダイアログを閉じて *Try again* |
| 取り込み中に Pro Tools が終了した | Pro Tools stopped during the import | 先にセッションを確認（一部のトラックが作成済みの可能性あり）してから再適用 |
| ファイルが移動された | Files not found（一覧付き） | 認識中なら該当トラックは自動で外れます |
| ドロップしたものに音声がない | No audio files found | — |
| エンジンが停止した | The TrackMate engine stopped | *Restart engine*（リストはそのまま） |
| ステムに拍がない（無音、リズムのステムがない） | No steady beat found | ドラムやリズムのステムを追加するか、Pro Tools でテンポを設定 |
| テンポのモデルをダウンロード中 | The tempo model is still downloading | ヘッダーのダウンロードが終わるまで待つ |

## アルゴリズム
<sub>[English](README.md#how-it-works)</sub>

### 1. トラック名の前処理
コード：[`engine/stem_engine/names.py`](engine/stem_engine/names.py)

1. **正規化：** Unicode NFKC を適用し、拡張子・BPM・キー・日付を取り除きます。
2. **Pro Tools が付けたサフィックスを除去**（なくなるまで繰り返し）：
   - テイク・クリップ番号（`_03`、`_04-01` など）
   - プレイリスト番号（`.04_09` など）
   - 複製マーク（`.dup1` など）
   - AudioSuite のタグ：テイク番号の直前にある `-タグ` で、辞書にない語（`-TCEx_01` など）
3. **分かち書き：** 区切り文字、大文字小文字の切り替わり（`SnareTop`）、英字と数字の境目、CJK と英字の境目で分割します。元の表記は保持し、必要ならそのまま使えるようにします。
4. **バッチ共通の接頭辞・接尾辞を除去：** すべてのファイルに共通する部分は多くの場合曲名（`MySong_`、`_Track1` など）なので削除します。ただし辞書にある語は残します。
5. **DAW の既定名：** `Audio 7`、`Untitled`、`オーディオ 3` のような名前は楽器を表さないため、そのまま音声による認識に回し、DAW の連番も残しません。

### 2. 4 段階の認識
| レイヤー | 方法 | コード | 採用条件 |
|---|---|---|---|
| A 既知の名前 | [`kb/mix_naming.json`](kb/mix_naming.json)：14 カテゴリ、191 楽器、英・中・日の別名と略語 約 2,100 件、さらにユーザーが教えた別名 | [`textmatch.py`](engine/stem_engine/textmatch.py) | 一致すれば採用（信頼度：高） |
| B スペル補正 | 一致しなかった語に rapidfuzz WRatio | 同上 | スコア ≥ 90、長さ ≥ 4、2 位と 5 点以上の差、かつ長さが近い（信頼度：中） |
| C AI による名前の読み取り | Qwen3-Embedding-0.6B（ONNX 8-bit）。クエリとインデックスに同じ指示文を付け、インデックスには「楽器ではない」アンカーも含めます | [`embed.py`](engine/stem_engine/embed.py) | 類似度 ≥ 0.86、差 ≥ 0.03、アンカーより上（信頼度：中）。0.62–0.86 はレイヤー D でカテゴリを確認 |
| D 音の聴き取り | PE-AV small 音声エンコーダー（ONNX 8-bit）で最も音量の大きい区間を処理し、16 クラスのプロトタイプ（12 カテゴリ、クリック、フルミックス、話し声、ノイズ）と比較。SigLIP logit と softmax で採点 | [`audio.py`](engine/stem_engine/audio.py) | 最上位クラスの確率 ≥ 0.15（カテゴリのみ、信頼度：低） |

**辞書照合の詳細：**
- 最長のフレーズを優先します（`bass drum` は bass ではなく kick になります）。
- 略語は単語として完全に一致したときだけ採用し、中国語・日本語は部分文字列で照合して長いものを優先します。
- 楽器名にも修飾語にもなる語（`room`、`dbl` など）は、他の楽器語と並ぶときは修飾語、単独のときだけ楽器として扱います。
- 1 文字だけの語は、それが名前全体のときだけ有効です。
- 1 つの名前に複数のカテゴリが現れたときは、音声で判断します。

**統合（[`pipeline.py`](engine/stem_engine/pipeline.py)）：**
- 辞書がカテゴリ語しか見つけられず、名前に他の語もあるとき（`Synthesized Bass`）、AI の第 1 候補が同じカテゴリのより具体的な楽器なら、AI の答えを使います（A+C）。
- AI がグレーゾーンにあるときは、音声のカテゴリが一致した場合だけ採用します（C+D）。
- どれでも判断できないときはカテゴリを OTHER とし、元の名前のまま要確認にします。
- 上位 5 件の候補は、決定した答え → 辞書のあいまい候補 → AI の順位（音声のカテゴリ確率で並べ替え）→ 音声カテゴリの代表楽器、の順に並びます。スコアは % で表示しますが、意味は出どころによって異なります（辞書は 100 %、AI は類似度、音声は確率）。

### 3. 命名規則
- **構成：** 標準名 ＋ 修飾語 ＋ 番号（例：`Snare Bottom 2`）。
  - 位置を表す修飾語は標準表記にそろえます：L/R/C、Top/Bottom、In/Out、DI/Amp。
  - それ以外の修飾語は元の表記を残します（例：`Fuzz`）。
- **保持モード：** *Keep unrecognised words* をオンにすると、認識できなかった語と Pro Tools のサフィックスを付け直します。
- **重複：** バッチ内で同じ名前があれば連番を付け、名前が数字で終わる場合は `-1`/`-2` を使います。
- **セッション内の既存名：** Pro Tools に同じ名前のトラックがあれば ` 2`、` 3` … とします（Pro Tools と同じく大文字小文字を区別）。

### 4. ステレオ解析
コード：[`stereo_analysis/stereo_analyzer.py`](stereo_analysis/stereo_analyzer.py)

- **原理：** パン位置、パンロー、極性にかかわらず、単一の音源なら (L, R) のサンプルは原点を通る 1 本の直線上に並びます。そのため 2×2 共分散行列のランク 1 残差 `10·log10(λmin/λmax)` で判定します。
- **モノラルへの復元：** 第 1 固有ベクトルからパン位置と極性がわかり、そこへ射影すれば打ち消し合いのないモノラル版が得られます。
- **音のあるフレームだけを使用：** 無音やフェードの影響を受けません。
- **その他の検出：** 相互相関でディレイのかかったモノラルを見つけます。

詳しくは[ステレオ解析レポート](docs/reports/stereo-analysis.md)を参照してください。

### 5. Pro Tools への取り込み（`/apply`）
コード：[`engine/stem_engine/apply.py`](engine/stem_engine/apply.py)、[`protools.py`](engine/stem_engine/protools.py)

1. **フォルダ：** カテゴリ順に Basic Folder を作成します。同名のフォルダがセッションにあれば再利用します。
2. **インポート：** 1 ファイルずつ取り込みます（ConvertAudio で、セッションのサンプルレートに自動変換）。毎回直前のトラックを選択してから取り込むので、フォルダ内の順番はリストと一致します。モノラル変換が必要なファイルは、先に一時ファイルに変換します。
3. **リネーム：** 取り込み前後のトラック ID の差分から新しいトラックを特定し、事前に重複がないことを確認した名前にすぐ変更します。
4. **カラー：** フォルダとトラックをカラーごとにまとめて設定します。
5. **検証：** トラック一覧を読み直し、各トラックの名前・フォルダ・カラーを確認します。

現在の PTSL にはバスを作成するコマンドがないため、出力ルーティングは自動設定しません。詳しくは[連携レポート](docs/reports/pro-tools-integration.md)を参照してください。

### 6. テンポ（`/tempo`）
コード：[`engine/stem_engine/tempo.py`](engine/stem_engine/tempo.py)

1. **音源：** ドラムとパーカッションのステム。なければベース、ギター、キーボード、シンセ。それもなければ全ステム。元の音量のまま 22.05 kHz のモノラルにミックスします（Beat This! のスペクトログラムは音量に依存し、小さいミックスをフルスケールまで上げると誤った拍が増えるため）。
2. **拍：** Beat This! `final0`（ONNX）が 1 秒 50 フレームで拍とダウンビートを予測します。30 秒ずつ重ねて処理し、前処理とピーク検出はオリジナルと同じです。各ピークは放物線でフレーム間の位置まで求めるので、拍の間隔が 20 ms 単位に丸められません。
3. **整理：** 拍間隔の中央値を基準に、前の拍から 0.7 間隔未満の拍（倍のテンポで取られた部分）を除き、ステムが止まっている部分には欠けた拍を補います。
4. **固定か可変か：** すべての拍に直線を当てはめます。どの拍も直線から 30 ms 以内なら安定したテンポで、BPM は直線の傾きです。そうでなければ平均値（全体の時間 ÷ 拍間隔の数）を表示します。
5. **MIDI：** テンポだけの MIDI ファイル（4 分音符 = 480 tick）。テンポ 1 つ、または検出したダウンビートの間に小節ごとに 1 つ（ダウンビートがなければ 4 拍ごと）。最初の拍より前は最初の小節のテンポを使い、拍子も書き込みます。
6. **Pro Tools：** PTSL にはテンポを設定するコマンドがありませんが、MIDI ファイルを取り込むと Pro Tools が *MIDI Import Options* を表示し、*Import tempo map from MIDI File* でセッションのテンポを置き換えます。OK でもキャンセルでも PTSL は成功を返すため、TrackMate は最後の拍の位置の Bars|Beats を読み取り（タイムライン選択を一時的に移動して戻します）、自分のテンポマップと照合します。

実際の 85 BPM のステムでは 85.00 BPM でした。同じドラムを区間ごとに速めると、テンポマップは 76.5、85.0、93.6、102.0 BPM（実際は 76.5、85、93.5、102）になりました。詳しくは[テンポ検出レポート](docs/reports/tempo-detection.md)を参照してください。

## システム構成
<sub>[English](README.md#architecture)</sub>

```
┌──────────────── TrackMate (Flutter: macOS / Windows) ───────────────┐
│ drop & open dialog (Swift / C++)                                    │
│ track list, top 5, colours, BPM, preview, alerts                    │
└───────────────┬─────────────────────────────────────────────────────┘
                │ HTTP, 127.0.0.1 only, new token on every start
┌───────────────▼──────────── Local engine (Python, PyInstaller) ─────┐
│ name preprocessing → layers A/B/C/D → merge                         │
│ stereo analysis, model download and checks, alias learning          │
│ onnxruntime: Qwen3-Embedding, PE-AV audio encoder, Beat This!       │
└───────────────┬─────────────────────────────────────────────────────┘
                │ gRPC (PTSL, localhost:31416)
┌───────────────▼─────────────────────────────────────────────────────┐
│ Pro Tools: read session, folders, import, rename, colour, tempo     │
└─────────────────────────────────────────────────────────────────────┘
```

- **起動：** アプリは同梱のエンジンを子プロセスとして起動し、エンジンの最初の出力行または `engine.json` からポートとトークンを取得します。
- **API のセキュリティ：** ローカル接続のみ受け付け、起動のたびに新しいトークンを発行し、Host がローカルでないリクエストは拒否します。エンドポイントは [`engine/README.md`](engine/README.md) を参照してください。

## ソースからのビルドとテスト
<sub>[English](README.md#building-from-source-and-testing)</sub>

必要なツール：
- [uv](https://docs.astral.sh/uv/)（Python 3.12）
- [Flutter 3.47.8](https://docs.flutter.dev/)
- macOS では Xcode、Windows では Visual Studio 2022（C++ によるデスクトップ開発）
- 統合テストには同じマシンに Pro Tools が必要

```bash
# エンジン
cd engine
uv sync --group dev
uv run pytest -q                       # 93 テスト（モデルが必要なテストは自動でスキップ）
uv run stem-engine                     # 起動。最初の行に {"port", "token"}、モデルのダウンロードを開始

# ステレオ解析
cd ../stereo_analysis
../engine/.venv/bin/python -m pytest -q   # 27 テスト

# アプリ（開発モード。上のエンジン環境を使用）
cd ../app
flutter test                            # 25 テスト。--exclude-tags golden でスクリーンショット比較を除外
flutter run -d macos --dart-define=ENGINE_CMD=$PWD/../engine/.venv/bin/stem-engine
```

**配布用パッケージの作成：**
- macOS：[`scripts/package-macos.sh`](scripts/package-macos.sh)。Apple Silicon 用と Intel 用のエンジンをそれぞれビルドし（Intel 用は Rosetta 2 上の x86_64 Python でビルドするため、Apple Silicon の Mac で実行できます）、1 つのユニバーサルアプリにまとめます。
- Windows：[`scripts/package-windows.ps1`](scripts/package-windows.ps1)
- どちらもエンジンをビルドしてスモークテストし、アプリをビルドしてエンジンを同梱し、`dist/` に出力します。

詳細は [`engine/README.md`](engine/README.md) と [`app/README.md`](app/README.md) を参照してください。

## リポジトリ構成
<sub>[English](README.md#repository-layout)</sub>

| パス | 内容 |
|---|---|
| [`app/`](app) | Flutter デスクトップアプリ：[UI](app/lib/ui)、[状態管理](app/lib/app_state.dart)、[エンジン起動](app/lib/engine/engine_launcher.dart)、[macOS ネイティブ](app/macos/Runner/MainFlutterWindow.swift)、[Windows ネイティブ](app/windows/runner/flutter_window.cpp)、[テスト](app/test) |
| [`engine/`](engine) | ローカルエンジン：[認識](engine/stem_engine)、[API](engine/stem_engine/api.py)、[Pro Tools](engine/stem_engine/protools.py)、[モデル一覧](engine/stem_engine/data/model_manifest.json)、[テスト](engine/tests)、[評価ツール](engine/tools)、[パッケージ化](engine/packaging) |
| [`stereo_analysis/`](stereo_analysis) | ステレオ／モノラル解析とテスト |
| [`kb/mix_naming.json`](kb/mix_naming.json) | 楽器名の辞書（カテゴリ、楽器、別名、略語、中国語・日本語、修飾語、あいまい語） |
| [`experiments/`](experiments) | 研究：[テキスト埋め込みモデルの比較](experiments/c_layer_embedding)、[楽器認識の評価](experiments/instrument_zeroshot) |
| [`tools/`](tools) | [Qwen の ONNX 変換](tools/qwen_onnx)、[PE-AV の ONNX 変換](tools/peav_onnx)、[Pro Tools 検証スクリプト](tools/ptsl_m0)、[PE-AV 楽器認識デモ](tools/peav_space)（Hugging Face Space のソース：169 種の楽器と音。[`app.py`](tools/peav_space/space/app.py)、[ラベルとプロンプト](tools/peav_space/space/labels.json)、[プロトタイプ生成スクリプト](tools/peav_space/build_prototypes.py)） |
| [`scripts/`](scripts) | macOS／Windows パッケージ作成スクリプト |
| [`docs/`](docs) | [研究とテストのレポート](docs/reports)、[スクリーンショット](docs/images) |
| [`.github/workflows/`](.github/workflows) | [CI](.github/workflows/ci.yml)、[パッケージ作成とリリース](.github/workflows/package.yml) |

## 研究とテストのレポート
<sub>[English](README.md#research-and-test-reports)</sub>

一覧：[`docs/reports/`](docs/reports/README.md)（レポートは繁体字中国語で書かれています）

| レポート | 要点 |
|---|---|
| [テキスト埋め込みモデルの比較](experiments/c_layer_embedding/REPORT.md) | 中国語は Qwen3-Embedding、日本語は bge-m3 が最良。上位 5 件のカバー率は Top-1 よりはるかに高く、候補の生成に向いている |
| [楽器認識の評価](experiments/instrument_zeroshot/REPORT.md) | PE-AV small は実際のソロ録音でカテゴリ正解率 96.2 %（バランス正解率 97.5 %） |
| [モデルの変換と量子化](docs/reports/model-export.md) | 2 つの ONNX モデルとも PyTorch との cosine ≥ 0.996。Qwen 8-bit は CPU で 1 件 54 ms |
| [ステレオ／モノラル解析](docs/reports/stereo-analysis.md) | 14 の合成ケース（パン、片側、逆相、ディレイ、リバーブ…）をすべて正しく判定 |
| [エンジンの評価](docs/reports/engine-evaluation.md) | 実際のトラック名で Top-1 96.6 %、Top-5 98.9 %。自動リネームの適合率 97.0 %、楽器以外の名前の誤リネームは 0 |
| [Pro Tools 連携テスト](docs/reports/pro-tools-integration.md) | 10 トラックの取り込み・リネーム・カラー設定が 8.2 秒、すべて検証に合格 |
| [テンポ検出](docs/reports/tempo-detection.md) | 拍は PyTorch 版と同じ。85 BPM のステムは 85.00、テンポマップの誤差は 0.15 BPM 以内。取り込み後に Pro Tools のテンポを確認 |
| [デスクトップアプリのテスト](docs/reports/app-testing.md) | 実アプリ ＋ エンジン ＋ Pro Tools のエンドツーエンドで 35–38 秒 |

## CI/CD
<sub>[English](README.md#cicd)</sub>

| Workflow | 実行タイミング | 内容 |
|---|---|---|
| [CI](.github/workflows/ci.yml) | `main` への push、プルリクエスト | エンジンとステレオ解析のテスト、`flutter analyze`、アプリのテスト（スクリーンショット比較を除く） |
| [Package](.github/workflows/package.yml) | `main` への push、`v*` タグ、手動 | エンジンをビルドしてスモークテスト（macOS：Apple Silicon 用と Intel 用を 1 つのユニバーサルアプリに同梱、Windows x64）し、アプリをビルドしてワークフローの成果物としてアップロード。`v*` タグでは GitHub Release を作成し、インストーラーとインストール手順（[テンプレート](.github/release-notes.md)）を添付 |

リリースの公開：
```bash
git tag v0.1.0
git push origin v0.1.0
```

## 既知の制限
<sub>[English](README.md#known-limitations)</sub>

- **出力ルーティング：** PTSL はまだバスを作成できないため、TrackMate はフォルダへのグループ分けだけを行います。ルーティングは手動で設定してください。
- **Windows：** CI でビルドとパッケージ作成はできていますが、実機ではまだ使われていません。ファイルをドラッグしたときのハイライト表示もありません。
- **macOS：** ad-hoc 署名で、Apple の公証は受けていません。Intel 用エンジンは Intel macOS 版が提供される最後のリリースである onnxruntime 1.23.2 を使います。評価結果は Apple Silicon 用と同じですが、テストは Rosetta 2 上のみで、実機の Intel Mac ではまだ試していません。
- **しきい値：** 現在の値は小さなテストセットから決めた初期値で、実際のセッションでの調整が必要です。
- **辞書：** 辞書にない中国語・日本語の表記は、主に辞書の拡充とユーザーの修正から学習します。
- **テンポ：** 拍はすべて 4 分音符として扱うため、半分や倍のテンポで取られた曲は ½× か 2× を選ぶ必要があります。1 曲の中で約 30 % を超えるテンポ変化には追従しません。x/4 以外の拍子は x/4 として書き込みます。テンポマップは小節線ではなく、最初に検出した拍から始まります。取り込みのたびに Pro Tools の *MIDI Import Options* で *OK* を 1 回押す必要があります。
- **音声認識：** カテゴリのみの判定で、ソロ録音でしか検証していません。CPU では 10 秒の区間に約 2.8 秒かかるため、名前から判断できないトラックにだけ使います。

## 謝辞
<sub>[English](README.md#acknowledgements)</sub>

TrackMate は以下のオープンソースソフトウェア、モデル、データセット、フォントを利用しています。作者とコミュニティの皆さまに感謝します。各ライセンスは元のプロジェクトに従います。

### モデル
| モデル | 作者 | ライセンス | 用途 |
|---|---|---|---|
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Qwen チーム（Alibaba） | Apache-2.0 | レイヤー C、名前の読み取り（ONNX 版：[aaatmy/Qwen3-Embedding-0.6B-ONNX](https://huggingface.co/aaatmy/Qwen3-Embedding-0.6B-ONNX)） |
| [PE-AV small](https://huggingface.co/facebook/pe-av-small)（Perception Encoder Audio-Visual） | Meta FAIR | Apache-2.0 | レイヤー D、音の聴き取り（ONNX 版：[aaatmy/pe-av-small-audio-ONNX](https://huggingface.co/aaatmy/pe-av-small-audio-ONNX)） |
| [Beat This!](https://github.com/CPJKU/beat_this)（`final0`） | Foscarin、Schlüter、Widmer（JKU Linz） | MIT | テンポ：拍とダウンビート（ONNX 版：[aaatmy/beat-this-onnx](https://huggingface.co/aaatmy/beat-this-onnx)） |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | Microsoft | MIT | 研究での比較 |
| [bge-m3](https://huggingface.co/BAAI/bge-m3) | BAAI | MIT | 研究での比較 |
| [larger_clap_general](https://huggingface.co/laion/larger_clap_general) | LAION | Apache-2.0 | 研究での比較 |

### データセット
| データセット | ライセンス | 用途 |
|---|---|---|
| [NSynth](https://magenta.tensorflow.org/datasets/nsynth)（Google Magenta） | CC BY 4.0 | 楽器認識の評価 |
| [Medley-solos-DB](https://zenodo.org/records/3464194)（Lostanlen & Cella） | CC BY 4.0 | 楽器認識の評価、音声のしきい値 |

### エンジン（Python）
| パッケージ | ライセンス |
|---|---|
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile)（[libsndfile](https://libsndfile.github.io/libsndfile/) を同梱、LGPL-2.1） | BSD-3-Clause |
| [python-soxr](https://github.com/dofuuz/python-soxr)（[libsoxr](https://sourceforge.net/projects/soxr/)） | LGPL-2.1-or-later |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT |
| [ONNX Runtime](https://onnxruntime.ai/) | MIT |
| [Hugging Face Tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 |
| [FastAPI](https://fastapi.tiangolo.com/)、[Pydantic](https://docs.pydantic.dev/) | MIT |
| [Starlette](https://www.starlette.io/)、[Uvicorn](https://www.uvicorn.org/) | BSD-3-Clause |
| [py-ptsl](https://github.com/iluvcapra/py-ptsl)（Jamie Hardt） | BSD-3-Clause |
| [gRPC](https://grpc.io/)（grpcio） | Apache-2.0 |
| [Protocol Buffers](https://protobuf.dev/) | BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org/)（パッケージ化。ブートローダー例外により同梱プログラムの配布が可能） | GPL-2.0 with bootloader exception |
| [pytest](https://pytest.org/)、[HTTPX](https://www.python-httpx.org/)（テスト） | MIT、BSD-3-Clause |
| [uv](https://docs.astral.sh/uv/)、[Hatchling](https://hatch.pypa.io/)（ビルドツール） | MIT / Apache-2.0、MIT |

研究とモデル変換では、ほかに [PyTorch](https://pytorch.org/)（BSD-3-Clause）、[Transformers](https://github.com/huggingface/transformers)、[Sentence Transformers](https://www.sbert.net/)、[timm](https://github.com/huggingface/pytorch-image-models)（Apache-2.0）、[librosa](https://librosa.org/)（ISC）、[Pillow](https://python-pillow.org/)（MIT-CMU）を使用しました。PE-AV デモでは、ほかに [Gradio](https://www.gradio.app/)、[huggingface_hub](https://github.com/huggingface/huggingface_hub)（Apache-2.0）、[FFmpeg](https://ffmpeg.org/)（LGPL-2.1+、その他の音声形式のデコード用）を使用しています。

### アプリ（Flutter）
| 項目 | ライセンス |
|---|---|
| [Flutter](https://flutter.dev/)、[http](https://pub.dev/packages/http) | BSD-3-Clause |
| [lucide_icons_flutter](https://pub.dev/packages/lucide_icons_flutter)（[Lucide](https://lucide.dev/) アイコン、ISC） | MIT |
| [Geist、Geist Mono](https://github.com/vercel/geist-font)（Vercel、v1.8.2。ライセンスは [`app/assets/fonts/Geist-OFL.txt`](app/assets/fonts/Geist-OFL.txt)） | SIL OFL 1.1 |

### 参考文献
BibTeX は[英語版](README.md#references)を参照してください。

### 商標
Pro Tools、AudioSuite、Avid は Avid Technology, Inc. の商標です。TrackMate は Avid と提携しておらず、Avid の承認も受けていません。Pro Tools Scripting Library（PTSL）は Avid が提供しています。

## ライセンス
<sub>[English](README.md#license)</sub>

TrackMate のソースコード、ドキュメント、命名辞書は [MIT ライセンス](LICENSE)で公開しています。

事前学習済みモデルには MIT ライセンスは**適用されません**。Qwen3-Embedding-0.6B と PE-AV small は Apache License 2.0、Beat This! は独自の MIT ライセンス（© JKU Linz）で提供されており、TrackMate はモデルと一緒にそのライセンスファイルもダウンロードします。PE-AV から生成したファイル（`peav_prototypes.npz`、`prototypes.npz`）も同じライセンスです。サードパーティのモデル、データセット、フォント、ライブラリのライセンスと、モデルに加えた変更は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) にまとめています。
