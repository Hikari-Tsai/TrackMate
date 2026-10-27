TrackMate recognises your stems, suggests standard track names, categories and colours, finds the tempo in the drum stems, and imports everything into Pro Tools in category folders.

## Download
| Platform | File |
|---|---|
| macOS 14 or later, Apple Silicon or Intel (universal) | [TrackMate-macos-universal.dmg](https://github.com/{{REPO}}/releases/download/{{TAG}}/TrackMate-macos-universal.dmg) ([.zip](https://github.com/{{REPO}}/releases/download/{{TAG}}/TrackMate-macos-universal.zip)) |
| Windows 10/11 x64 | [TrackMate-windows-x64.zip](https://github.com/{{REPO}}/releases/download/{{TAG}}/TrackMate-windows-x64.zip) |

You also need Pro Tools 2023.3 or later (with the Pro Tools Scripting Library), and about 1.43 GB of disk space for the models downloaded on first start.

## Install
**macOS**
1. Open the `.dmg` and drag `TrackMate.app` into Applications.
2. This build is not notarized by Apple. The first time, right-click the app and choose **Open**, or run:
   ```bash
   xattr -dr com.apple.quarantine /Applications/TrackMate.app
   ```

**Windows**
1. Unzip the whole folder and run `TrackMate.exe`. Keep the `engine` folder next to it.
2. If SmartScreen warns you, choose **More info** → **Run anyway**.

**First start:** TrackMate downloads its models in the background and shows the progress in its header. Known track names and spelling correction already work during the download.

## Use
1. Open Pro Tools and the session to import into.
2. Drag stems or folders into TrackMate, or press **Add audio files**.
3. Check the suggested names, categories, colours and mono conversions. Rows in orange need a look.
4. Press **Preview & apply**, check the plan, then apply. TrackMate creates the folders, imports, renames and colours the tracks, and verifies the result.
5. Optional: press **Detect BPM** (top right) to see the tempo, choose a constant tempo or a tempo map, and import it. In Pro Tools' *MIDI Import Options* dialog, keep *Import tempo map from MIDI File* ticked and press **OK**; TrackMate then checks the session tempo.

Full guide: [README](https://github.com/{{REPO}}/blob/{{TAG}}/README.md#usage) · [繁體中文](https://github.com/{{REPO}}/blob/{{TAG}}/README.zh-TW.md) · [日本語](https://github.com/{{REPO}}/blob/{{TAG}}/README.ja.md)

<details>
<summary>繁體中文</summary>

**下載：** macOS 14 以上（Apple Silicon 和 Intel 通用）請下載 `TrackMate-macos-universal.dmg`；Windows 10/11 x64 請下載 `TrackMate-windows-x64.zip`。需要 Pro Tools 2023.3 以上，第一次啟動會下載約 1.43 GB 的模型。

**安裝：**
- **macOS：** 打開 `.dmg`，把 `TrackMate.app` 拖進「應用程式」。這個版本沒有經過 Apple 公證，第一次開啟請在 App 上按右鍵 →「打開」，或在終端機執行上面的 `xattr` 指令。
- **Windows：** 解壓縮整個資料夾後執行 `TrackMate.exe`，`engine` 資料夾要留在旁邊。出現 SmartScreen 警告時，選「其他資訊」→「仍要執行」。

**使用：** 開啟 Pro Tools 和要匯入的 session → 把分軌檔拖進 TrackMate → 確認名稱、大類、顏色和轉單聲道（橘色的列需要確認）→ 按 **Preview & apply** 確認後套用。需要設定速度時，按右上角的 **Detect BPM**，選固定速度或速度圖後匯入，在 Pro Tools 的 *MIDI Import Options* 保持勾選 *Import tempo map from MIDI File* 並按 **OK**。

</details>

<details>
<summary>日本語</summary>

**ダウンロード：** macOS 14 以降（Apple Silicon と Intel に対応）は `TrackMate-macos-universal.dmg`、Windows 10/11 x64 は `TrackMate-windows-x64.zip` をダウンロードしてください。Pro Tools 2023.3 以降が必要です。初回起動時に約 1.43 GB のモデルをダウンロードします。

**インストール：**
- **macOS：** `.dmg` を開き、`TrackMate.app` を「アプリケーション」にドラッグします。このビルドは Apple の公証を受けていないため、初回はアプリを右クリックして「開く」を選ぶか、上の `xattr` コマンドを実行してください。
- **Windows：** フォルダごと解凍して `TrackMate.exe` を起動します。`engine` フォルダは同じ場所に置いたままにしてください。SmartScreen の警告が出たら「詳細情報」→「実行」を選びます。

**使い方：** Pro Tools と取り込み先のセッションを開く → ステムを TrackMate にドラッグ → 名前・カテゴリ・カラー・モノラル変換を確認（オレンジの行は要確認）→ **Preview & apply** で確認して適用。テンポを設定するには右上の **Detect BPM** を押し、固定テンポかテンポマップを選んで取り込みます。Pro Tools の *MIDI Import Options* では *Import tempo map from MIDI File* をオンのまま **OK** を押してください。

</details>
