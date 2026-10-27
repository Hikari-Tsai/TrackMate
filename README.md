<p align="center"><img src="docs/images/trackmate_icon.png" width="128" alt="TrackMate icon"></p>

<p align="center"><b>English</b> | <a href="README.zh-TW.md">繁體中文</a> | <a href="README.ja.md">日本語</a></p>

# TrackMate

TrackMate takes care of the most tedious part of preparing a Pro Tools mix: stem files with inconsistent names full of typos and abbreviations, and tracks that are really mono but were exported as stereo.

It recognises the instrument on every stem, proposes a standard name, a category and a colour, and decides whether the file should be turned back into mono. After you confirm, one click imports everything into Pro Tools: folders per category, import, rename, colour.

Recognition combines rules and AI models:
- **Rules:** a dictionary of common track names and a spelling corrector.
- **Reading the name:** the multilingual text-embedding model Qwen3-Embedding-0.6B understands track names it has never seen.
- **Listening:** Meta's pretrained audio–text model PE-AV (in the same family as CLAP; only the audio encoder, converted to ONNX) handles tracks whose names say nothing.

On a test set of real-world track names, the top-1 accuracy is 96.6 %, and the right answer is among the top 5 in 98.9 % of cases.

TrackMate does not drive Pro Tools by simulating mouse clicks with AppleScript. It uses Avid's official Pro Tools Scripting Library (PTSL), which is far less sensitive to interface changes and keeps working across future versions.

![TrackMate track list](docs/images/track_list.png)

- **Four recognition layers:** known track names → spelling → AI name reading → listening. Chinese, English and Japanese names all work; tracks whose names say nothing (for example `Audio 3`) are recognised from their audio.
- **You decide where it is unsure:** every track shows its top-1 result and a confidence level; a menu lists the top 5, and you can type a name, search all instruments, keep the original name, or change the category and colour.
- **Stereo analysis:** detects fake stereo, one-sided stereo, inverted polarity and delays, and converts to mono where needed.
- **Pro Tools integration:** works through PTSL; names are kept unique, and after applying, every track's name, folder and colour are verified.
- **Runs entirely on your computer:** the models are downloaded on first start; after that no network is needed.

---

## Contents
- [Download and install](#download-and-install)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Building from source and testing](#building-from-source-and-testing)
- [Repository layout](#repository-layout)
- [Research and test reports](#research-and-test-reports)
- [CI/CD](#cicd)
- [Known limitations](#known-limitations)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Download and install

### Requirements
| Item | Requirement |
|---|---|
| macOS | Apple Silicon (M series), macOS 12 or later |
| Windows | Windows 10/11 x64 (built in CI, not yet verified on a real machine; see [Known limitations](#known-limitations)) |
| Pro Tools | A version with PTSL (2023.3 or later); tested with Pro Tools 26.4.1. Colouring needs a PTSL with `SetTrackColor` |
| Disk space | About 150 MB for the app, plus about 1.35 GB of models downloaded on first start |

### Install
1. Download the latest version from [Releases](../../releases):
   - macOS: `TrackMate-macos-arm64.dmg` (or `.zip`)
   - Windows: `TrackMate-windows-x64.zip`
2. **macOS:** drag `TrackMate.app` into Applications. The current builds are not notarized by Apple, so the first time, right-click the app and choose **Open**, or run:
   ```bash
   xattr -dr com.apple.quarantine /Applications/TrackMate.app
   ```
3. **Windows:** unzip and run `TrackMate.exe`. If SmartScreen warns you, choose **More info** → **Run anyway**.
4. **First start:** the app downloads the models in the background and shows the progress in its header. Known track names and spelling correction work before the download finishes. Models and settings are stored in:
   - macOS: `~/Library/Application Support/TrackMate`
   - Windows: `%APPDATA%\TrackMate`

## Usage

![Empty state](docs/images/empty_state.png)

1. **Open Pro Tools and the session to import into.** The session name and sample rate are shown under the title.
2. **Add stems:** drag audio files or folders into the window, or press **Add audio files**. Supported: WAV, AIFF, MP3, FLAC, M4A, OGG, CAF.
3. **Check the results:**
   - Name-based results appear first; tracks whose names say nothing are then recognised by listening (shown as *Listening…*).
   - Tracks with low confidence are highlighted in orange, and the header shows how many need review. Hover over the confidence column to see how a track was recognised.
4. **Correct:**
   - **New name menu (top 5):** pick another candidate, or choose *Type a name…*, *Search all instruments…* or *Keep original name*. You can also edit the name field directly.
   - **Category:** changing it also switches the colour to that category's default.
   - **Colour swatch:** pick any of the 69 Pro Tools palette colours.
   - **To mono:** pre-ticked from the stereo analysis; you can change it.
   - Instruments you pick from the top 5 are remembered, so the same name is recognised correctly next time.
5. **Keep unrecognised words (off by default):** when off, words that could not be recognised and Pro Tools suffixes (such as `_04-01` or `-TCEx_01`) are removed; turn it on to keep them. Duplicate names get running numbers, for example `Lead Vocal 1`, `Lead Vocal 2`.
6. **Press Preview & apply:** you first see which folders will be created, each track's final name and whether it is converted to mono. Nothing is written to Pro Tools until you confirm. Afterwards, every track shows its verification result.

![Category menu](docs/images/category_menu.png)

When something goes wrong, the app explains what happened and what to do:

![Alert when Pro Tools is not running](docs/images/alert_pro_tools.png)

| Situation | Alert | What you can do |
|---|---|---|
| Pro Tools is not running | Pro Tools is not running | Start Pro Tools, then *Try again* |
| No session is open | No session is open in Pro Tools | Open a session, then *Try again* |
| Pro Tools is busy or shows a dialog | Pro Tools is not responding | Close the dialog, then *Try again* |
| Pro Tools quits during the import | Pro Tools stopped during the import | Check the session first (some tracks may already be there), then apply again |
| Files were moved | Files not found (with the list) | During recognition those tracks are removed automatically |
| Nothing dropped is audio | No audio files found | — |
| The engine stopped | The TrackMate engine stopped | *Restart engine* (your list is kept) |

## How it works

### 1. Name preprocessing
Code: [`engine/stem_engine/names.py`](engine/stem_engine/names.py)

1. **Normalisation:** Unicode NFKC; file extension, BPM, key and dates are removed.
2. **Pro Tools suffixes are removed** (repeatedly, until none is left):
   - take and clip numbers such as `_03` or `_04-01`;
   - playlist numbers such as `.04_09`;
   - duplicate marks such as `.dup1`;
   - AudioSuite tags: `-Tag` followed by a take number, when the dictionary does not know the word, such as `-TCEx_01`.
3. **Tokenisation:** split at separators, case changes (`SnareTop`), letter/digit boundaries and CJK/Latin boundaries. The original spelling is kept so it can be reused verbatim.
4. **Batch prefixes and suffixes are removed:** text shared by every file in the batch is usually the song title (for example `MySong_` or `_Track1`) and is removed, except words the dictionary knows.
5. **DAW default names:** names such as `Audio 7`, `Untitled` or `オーディオ 3` say nothing about the instrument; they go straight to audio recognition, and the DAW's counter is not kept.

### 2. Four recognition layers
| Layer | Method | Code | Accepted when |
|---|---|---|---|
| A Known names | [`kb/mix_naming.json`](kb/mix_naming.json): 14 categories, 191 instruments, about 2,100 English, Chinese and Japanese aliases and abbreviations, plus the aliases you taught it | [`textmatch.py`](engine/stem_engine/textmatch.py) | A match is accepted (high confidence) |
| B Spelling | rapidfuzz WRatio on the words nothing matched | same | Score ≥ 90, length ≥ 4, at least 5 points ahead of the runner-up, and similar length (medium confidence) |
| C AI name reading | Qwen3-Embedding-0.6B (ONNX, 8-bit). Queries and index carry the same instruction; the index also contains "not an instrument" anchors | [`embed.py`](engine/stem_engine/embed.py) | Similarity ≥ 0.86, lead ≥ 0.03, and above the anchors (medium confidence); 0.62–0.86 goes to layer D to confirm the category |
| D Listening | PE-AV small audio encoder (ONNX, 8-bit) on the loudest segments, compared with 16 class prototypes (12 categories, click, full mix, speech, noise); SigLIP logits with a softmax | [`audio.py`](engine/stem_engine/audio.py) | Best class probability ≥ 0.15 (category only, low confidence) |

**Dictionary matching details:**
- The longest phrase wins (`bass drum` matches kick, not bass).
- Abbreviations must be whole words; Chinese and Japanese terms match as substrings, longest first.
- Words that are both an instrument and a modifier (such as `room` or `dbl`) are modifiers next to another instrument word, and instruments only when they stand alone.
- A single letter counts only when it is the whole name.
- When several categories appear in one name, the audio decides.

**Merging ([`pipeline.py`](engine/stem_engine/pipeline.py)):**
- When the dictionary finds only a family word and the name has more words (`Synthesized Bass`), and the AI's best match is a more specific instrument of the same family, the AI's answer is used (A+C).
- In the AI's grey zone, a result is accepted only when the audio agrees on the category (C+D).
- When nothing works, the category is OTHER, the original name is kept and the track is flagged for review.
- Top-5 candidates come, in order, from: the decision → the dictionary's ambiguous options → the AI ranking (re-ordered with the audio category probabilities) → the audio categories' representative instruments. Scores are shown as percentages, but their meaning depends on the source: 100 % for the dictionary, similarity for the AI, probability for the audio.

### 3. Naming
- **Form:** standard name + modifiers + number, for example `Snare Bottom 2`.
  - Placement modifiers are standardised: L/R/C, Top/Bottom, In/Out, DI/Amp.
  - Other modifiers keep your spelling, for example `Fuzz`.
- **Keep mode:** with *Keep unrecognised words* on, unrecognised words and Pro Tools suffixes are added back.
- **Duplicates:** names repeated in the batch get running numbers; when a name already ends in a number, `-1`/`-2` is used.
- **Names taken in the session:** names that already exist in Pro Tools become ` 2`, ` 3`, … (case-sensitive, as in Pro Tools).

### 4. Stereo analysis
Code: [`stereo_analysis/stereo_analyzer.py`](stereo_analysis/stereo_analyzer.py)

- **Principle:** whatever the pan position, pan law or polarity, a single source puts every (L, R) sample on one line through the origin, so the decision uses the rank-1 residual of the 2×2 covariance matrix, `10·log10(λmin/λmax)`.
- **Mono recovery:** the principal eigenvector gives pan position and polarity; projecting onto it gives a mono version that never cancels.
- **Only active frames:** statistics use only frames with sound, so silence and fades do not bias the result.
- **Other checks:** cross-correlation finds delayed mono.

Details: [stereo report](docs/reports/stereo-analysis.md).

### 5. Import into Pro Tools (`/apply`)
Code: [`engine/stem_engine/apply.py`](engine/stem_engine/apply.py), [`protools.py`](engine/stem_engine/protools.py)

1. **Folders:** one Basic Folder per category, in category order; a folder that already exists in the session is reused.
2. **Import:** file by file (ConvertAudio, so everything is converted to the session's sample rate), each time after selecting the previous track, so the order inside the folder matches the list. Files to be converted to mono are converted to a temporary file first.
3. **Rename:** the new track is found from the track IDs before and after the import and renamed at once, to a name already checked to be unique.
4. **Colour:** folders and tracks are coloured in groups by colour.
5. **Verification:** the track list is read again and each track's name, folder and colour are checked.

PTSL currently has no command to create buses, so output routing is not set automatically. See the [integration report](docs/reports/pro-tools-integration.md).

## Architecture

```
┌──────────────── TrackMate (Flutter: macOS / Windows) ───────────────┐
│ drop & open dialog (Swift / C++)                                    │
│ track list, top 5, colours, preview, alerts                         │
└───────────────┬─────────────────────────────────────────────────────┘
                │ HTTP, 127.0.0.1 only, new token on every start
┌───────────────▼──────────── Local engine (Python, PyInstaller) ─────┐
│ name preprocessing → layers A/B/C/D → merge                         │
│ stereo analysis, model download and checks, alias learning          │
│ onnxruntime: Qwen3-Embedding, PE-AV audio encoder                   │
└───────────────┬─────────────────────────────────────────────────────┘
                │ gRPC (PTSL, localhost:31416)
┌───────────────▼─────────────────────────────────────────────────────┐
│ Pro Tools: read session, create folders, import, rename, colour     │
└─────────────────────────────────────────────────────────────────────┘
```

- **Start-up:** the app starts its bundled engine as a child process and reads the port and token from the engine's first output line or from `engine.json`.
- **API security:** local connections only; a new token on every start; requests whose Host is not local are refused. Endpoints are described in [`engine/README.md`](engine/README.md).

## Building from source and testing

Tools:
- [uv](https://docs.astral.sh/uv/) (Python 3.12).
- [Flutter 3.47.8](https://docs.flutter.dev/).
- Xcode on macOS; Visual Studio 2022 with C++ desktop development on Windows.
- Pro Tools on the machine for the integration tests.

```bash
# Engine
cd engine
uv sync --group dev
uv run pytest -q                       # 80 tests (tests that need the models skip themselves)
uv run stem-engine                     # starts; first line {"port", "token"}; downloads the models

# Stereo analysis
cd ../stereo_analysis
../engine/.venv/bin/python -m pytest -q   # 27 tests

# App (development mode, using the engine environment above)
cd ../app
flutter test                            # 25 tests; add --exclude-tags golden to skip screenshot comparisons
flutter run -d macos --dart-define=ENGINE_CMD=$PWD/../engine/.venv/bin/stem-engine
```

**Packaging the app for distribution:**
- macOS: [`scripts/package-macos.sh`](scripts/package-macos.sh).
- Windows: [`scripts/package-windows.ps1`](scripts/package-windows.ps1).
- Both build the engine, smoke-test it, build the app, put the engine inside, and write the result to `dist/`.

More in [`engine/README.md`](engine/README.md) and [`app/README.md`](app/README.md).

## Repository layout

| Path | Contents |
|---|---|
| [`app/`](app) | Flutter desktop app: [UI](app/lib/ui), [state](app/lib/app_state.dart), [engine launcher](app/lib/engine/engine_launcher.dart), [macOS native code](app/macos/Runner/MainFlutterWindow.swift), [Windows native code](app/windows/runner/flutter_window.cpp), [tests](app/test) |
| [`engine/`](engine) | Local engine: [recognition](engine/stem_engine), [API](engine/stem_engine/api.py), [Pro Tools](engine/stem_engine/protools.py), [model manifest](engine/stem_engine/data/model_manifest.json), [tests](engine/tests), [evaluation tools](engine/tools), [packaging](engine/packaging) |
| [`stereo_analysis/`](stereo_analysis) | Stereo/mono analysis and its tests |
| [`kb/mix_naming.json`](kb/mix_naming.json) | Instrument naming dictionary (categories, instruments, aliases, abbreviations, Chinese and Japanese, modifiers, ambiguous terms) |
| [`experiments/`](experiments) | Research: [text-embedding model comparison](experiments/c_layer_embedding), [instrument recognition evaluation](experiments/instrument_zeroshot) |
| [`tools/`](tools) | [Qwen ONNX export](tools/qwen_onnx), [PE-AV ONNX export](tools/peav_onnx), [Pro Tools probes](tools/ptsl_m0), [PE-AV instrument recognition demo](tools/peav_space) (Hugging Face Space source: 169 instruments and sounds; [`app.py`](tools/peav_space/space/app.py), [labels and prompts](tools/peav_space/space/labels.json), [prototype builder](tools/peav_space/build_prototypes.py)) |
| [`scripts/`](scripts) | macOS and Windows packaging scripts |
| [`docs/`](docs) | [Research and test reports](docs/reports), [screenshots](docs/images) |
| [`.github/workflows/`](.github/workflows) | [CI](.github/workflows/ci.yml), [packaging and release](.github/workflows/package.yml) |

## Research and test reports

Index: [`docs/reports/`](docs/reports/README.md) (the reports are written in Traditional Chinese).

| Report | Key findings |
|---|---|
| [Text-embedding model comparison](experiments/c_layer_embedding/REPORT.md) | Qwen3-Embedding is best on Chinese, bge-m3 on Japanese; top-5 coverage is much higher than top-1, so the model works well as a candidate generator |
| [Instrument recognition evaluation](experiments/instrument_zeroshot/REPORT.md) | PE-AV small reaches 96.2 % category accuracy on real solo recordings (97.5 % balanced) |
| [Model export and quantisation](docs/reports/model-export.md) | Both ONNX models stay at cosine ≥ 0.996 against PyTorch; Qwen 8-bit takes 54 ms per query on CPU |
| [Stereo/mono analysis](docs/reports/stereo-analysis.md) | All 14 synthetic cases (pan, one-sided, inverted polarity, delay, reverb, …) are classified correctly |
| [Engine evaluation](docs/reports/engine-evaluation.md) | Real track names: top-1 96.6 %, top-5 98.9 %; automatic renames 97.0 % precise, no non-instrument name renamed |
| [Pro Tools integration](docs/reports/pro-tools-integration.md) | 10 tracks imported, renamed and coloured in 8.2 s, all verified |
| [Desktop app testing](docs/reports/app-testing.md) | Real app + engine + Pro Tools end to end in 35–38 s |

## CI/CD

| Workflow | Runs on | What it does |
|---|---|---|
| [CI](.github/workflows/ci.yml) | Push to `main`, pull requests | Engine and stereo-analysis tests, `flutter analyze`, app tests (without screenshot comparisons) |
| [Package](.github/workflows/package.yml) | Push to `main`, `v*` tags, manual | Builds and smoke-tests the engine on macOS (Apple Silicon) and Windows, builds the app and uploads it as a workflow artifact; a `v*` tag also creates a GitHub release with the installers |

To publish a release:
```bash
git tag v0.1.0
git push origin v0.1.0
```

## Known limitations
- **Output routing:** PTSL cannot create buses yet, so TrackMate only groups tracks into folders; set up routing yourself.
- **Windows:** built and packaged in CI but not yet used on a real machine; dragging files shows no hover highlight.
- **macOS:** Apple Silicon only; builds are ad-hoc signed and not notarized by Apple.
- **Thresholds:** current values are starting points from small test sets and still need calibration on real sessions.
- **Dictionary:** Chinese and Japanese spellings that are not in the dictionary are learnt mainly by extending it and from your corrections.
- **Audio recognition:** category only, and verified on solo recordings only. A 10-second segment takes about 2.8 s on CPU, so it runs only for tracks whose names say nothing.

## Acknowledgements

TrackMate is built on the following open-source software, models, datasets and fonts. Many thanks to their authors and communities. The licences of the original projects apply.

### Models
| Model | Authors | Licence | Use |
|---|---|---|---|
| [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Qwen team (Alibaba) | Apache-2.0 | Layer C, AI name reading (ONNX: [aaatmy/Qwen3-Embedding-0.6B-ONNX](https://huggingface.co/aaatmy/Qwen3-Embedding-0.6B-ONNX)) |
| [PE-AV small](https://huggingface.co/facebook/pe-av-small) (Perception Encoder Audio-Visual) | Meta FAIR | Apache-2.0 | Layer D, listening (ONNX: [aaatmy/pe-av-small-audio-ONNX](https://huggingface.co/aaatmy/pe-av-small-audio-ONNX)) |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | Microsoft | MIT | Research comparison |
| [bge-m3](https://huggingface.co/BAAI/bge-m3) | BAAI | MIT | Research comparison |
| [larger_clap_general](https://huggingface.co/laion/larger_clap_general) | LAION | Apache-2.0 | Research comparison |

### Datasets
| Dataset | Licence | Use |
|---|---|---|
| [NSynth](https://magenta.tensorflow.org/datasets/nsynth) (Google Magenta) | CC BY 4.0 | Instrument recognition evaluation |
| [Medley-solos-DB](https://zenodo.org/records/3464194) (Lostanlen & Cella) | CC BY 4.0 | Instrument recognition evaluation, audio threshold |

### Engine (Python)
| Package | Licence |
|---|---|
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile) (bundles [libsndfile](https://libsndfile.github.io/libsndfile/), LGPL-2.1) | BSD-3-Clause |
| [python-soxr](https://github.com/dofuuz/python-soxr) ([libsoxr](https://sourceforge.net/projects/soxr/)) | LGPL-2.1-or-later |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT |
| [ONNX Runtime](https://onnxruntime.ai/) | MIT |
| [Hugging Face Tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 |
| [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/) | MIT |
| [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/) | BSD-3-Clause |
| [py-ptsl](https://github.com/iluvcapra/py-ptsl) (Jamie Hardt) | BSD-3-Clause |
| [gRPC](https://grpc.io/) (grpcio) | Apache-2.0 |
| [Protocol Buffers](https://protobuf.dev/) | BSD-3-Clause |
| [PyInstaller](https://pyinstaller.org/) (packaging; the bootloader exception allows distributing bundled programs) | GPL-2.0 with bootloader exception |
| [pytest](https://pytest.org/), [HTTPX](https://www.python-httpx.org/) (tests) | MIT, BSD-3-Clause |
| [uv](https://docs.astral.sh/uv/), [Hatchling](https://hatch.pypa.io/) (build tools) | MIT / Apache-2.0, MIT |

Research and model export also used [PyTorch](https://pytorch.org/) (BSD-3-Clause), [Transformers](https://github.com/huggingface/transformers), [Sentence Transformers](https://www.sbert.net/), [timm](https://github.com/huggingface/pytorch-image-models) (Apache-2.0), [librosa](https://librosa.org/) (ISC) and [Pillow](https://python-pillow.org/) (MIT-CMU). The PE-AV demo also uses [Gradio](https://www.gradio.app/), [huggingface_hub](https://github.com/huggingface/huggingface_hub) (Apache-2.0) and [FFmpeg](https://ffmpeg.org/) (LGPL-2.1+, for decoding other audio formats).

### App (Flutter)
| Item | Licence |
|---|---|
| [Flutter](https://flutter.dev/), [http](https://pub.dev/packages/http) | BSD-3-Clause |
| [lucide_icons_flutter](https://pub.dev/packages/lucide_icons_flutter) ([Lucide](https://lucide.dev/) icons, ISC) | MIT |
| [Geist, Geist Mono](https://github.com/vercel/geist-font) (Vercel, v1.8.2; licence in [`app/assets/fonts/Geist-OFL.txt`](app/assets/fonts/Geist-OFL.txt)) | SIL OFL 1.1 |

### References
```bibtex
@article{qwen3embedding,
  title   = {Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models},
  author  = {Zhang, Yanzhao and Li, Mingxin and Long, Dingkun and Zhang, Xin and Lin, Huan and Yang, Baosong and Xie, Pengjun and Yang, An and Liu, Dayiheng and Lin, Junyang and Huang, Fei and Zhou, Jingren},
  journal = {arXiv preprint arXiv:2506.05176},
  year    = {2025}
}
@misc{vyas2025peav,
  title  = {Pushing the Frontier of Audiovisual Perception with Large-Scale Multimodal Correspondence Learning},
  author = {Vyas, Apoorv and Chang, Heng-Jui and Yang, Cheng-Fu and Huang, Po-Yao and Gao, Luya and Richter, Julius and Chen, Sanyuan and Le, Matt and Doll{\'a}r, Piotr and Feichtenhofer, Christoph and Lee, Ann and Hsu, Wei-Ning},
  year   = {2025},
  eprint = {2512.19687},
  archivePrefix = {arXiv}
}
@inproceedings{wu2023clap,
  title     = {Large-scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation},
  author    = {Wu, Yusong and Chen, Ke and Zhang, Tianyu and Hui, Yuchen and Berg-Kirkpatrick, Taylor and Dubnov, Shlomo},
  booktitle = {ICASSP},
  year      = {2023}
}
@article{wang2024me5,
  title   = {Multilingual E5 Text Embeddings: A Technical Report},
  author  = {Wang, Liang and Yang, Nan and Huang, Xiaolong and Yang, Linjun and Majumder, Rangan and Wei, Furu},
  journal = {arXiv preprint arXiv:2402.05672},
  year    = {2024}
}
@article{chen2024bgem3,
  title   = {BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation},
  author  = {Chen, Jianlv and Xiao, Shitao and Zhang, Peitian and Luo, Kun and Lian, Defu and Liu, Zheng},
  journal = {arXiv preprint arXiv:2402.03216},
  year    = {2024}
}
@inproceedings{engel2017nsynth,
  title     = {Neural Audio Synthesis of Musical Notes with WaveNet Autoencoders},
  author    = {Engel, Jesse and Resnick, Cinjon and Roberts, Adam and Dieleman, Sander and Eck, Douglas and Simonyan, Karen and Norouzi, Mohammad},
  booktitle = {ICML},
  year      = {2017}
}
@inproceedings{lostanlen2016medleysolos,
  title     = {Deep Convolutional Networks on the Pitch Spiral for Musical Instrument Recognition},
  author    = {Lostanlen, Vincent and Cella, Carmine-Emanuele},
  booktitle = {ISMIR},
  year      = {2016}
}
```

### Trademarks
Pro Tools, AudioSuite and Avid are trademarks of Avid Technology, Inc. TrackMate is not affiliated with or endorsed by Avid. The Pro Tools Scripting Library (PTSL) is provided by Avid.

## License
No license has been chosen for this project yet; until a LICENSE file is added, all rights are reserved. Third-party licences are listed under [Acknowledgements](#acknowledgements).
