# Third-party notices

TrackMate's own source code, documentation and naming dictionary ([`kb/mix_naming.json`](kb/mix_naming.json)) are released under the [MIT License](LICENSE). The MIT License does **not** cover the third-party models, data, fonts and libraries listed here. Each stays under its own licence, as stated below.

## Pretrained models

The models are not stored in this repository. TrackMate downloads them on first run from the Hugging Face repositories below, at the pinned revisions in [`model_manifest.json`](engine/stem_engine/data/model_manifest.json), together with a copy of their licence (`LICENSE`). They are stored in the TrackMate folder (macOS `~/Library/Application Support/TrackMate/models`, Windows `%APPDATA%\TrackMate\models`).

| Model | Original | Copyright | Licence | Downloaded copy |
|---|---|---|---|---|
| Qwen3-Embedding-0.6B | [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Alibaba Cloud (Qwen team) | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | [aaatmy/Qwen3-Embedding-0.6B-ONNX](https://huggingface.co/aaatmy/Qwen3-Embedding-0.6B-ONNX) |
| PE-AV small (Perception Encoder Audio-Visual) | [facebook/pe-av-small](https://huggingface.co/facebook/pe-av-small) | Meta Platforms, Inc. | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | [aaatmy/pe-av-small-audio-ONNX](https://huggingface.co/aaatmy/pe-av-small-audio-ONNX) |
| Beat This! (checkpoint `final0`) | [CPJKU/beat_this](https://github.com/CPJKU/beat_this) | Institute of Computational Perception, JKU Linz | [MIT License](https://github.com/CPJKU/beat_this/blob/main/LICENSE) | [aaatmy/beat-this-onnx](https://huggingface.co/aaatmy/beat-this-onnx) |

**Changes made to the original models** (Apache License 2.0, section 4b):
- **Qwen3-Embedding-0.6B:** exported to ONNX (last-token pooling and L2 normalisation built in), and the weights quantised to 8 bits. The weights are otherwise unchanged. The export and quantisation scripts are in [`tools/qwen_onnx`](tools/qwen_onnx), and in the `export/` folder of the downloaded copy.
- **PE-AV small:** only the audio encoder was exported to ONNX, and its weights quantised to 8 bits. The text and video encoders are not distributed. `scoring.json` holds the model's own logit scale and bias. The scripts are in [`tools/peav_onnx`](tools/peav_onnx), and in the `export/` folder of the downloaded copy.
- **Beat This!:** the `final0` checkpoint exported to ONNX at full precision (FP32), unchanged otherwise; `frontend.json` holds the mel filters and window of the original preprocessing. The downloaded copy keeps the original MIT licence and copyright notice.
- The original repositories have no NOTICE file.

### Data derived from PE-AV
These files contain text embeddings computed with the PE-AV small text encoder. They are derived from PE-AV and are distributed under the Apache License 2.0, not the MIT License:
- [`engine/stem_engine/data/peav_prototypes.npz`](engine/stem_engine/data/peav_prototypes.npz) (built by [`engine/tools/build_peav_prototypes.py`](engine/tools/build_peav_prototypes.py))
- [`tools/peav_space/space/prototypes.npz`](tools/peav_space/space/prototypes.npz) (built by [`tools/peav_space/build_prototypes.py`](tools/peav_space/build_prototypes.py))

### Models used only in research
These were compared in [`experiments/`](experiments) and are not used or distributed by TrackMate: [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) (MIT), [bge-m3](https://huggingface.co/BAAI/bge-m3) (MIT), [larger_clap_general](https://huggingface.co/laion/larger_clap_general) (Apache-2.0).

## Datasets
The datasets are not included in this repository; it contains only evaluation results computed from them.

| Dataset | Creators | Licence |
|---|---|---|
| [NSynth](https://magenta.tensorflow.org/datasets/nsynth) | Jesse Engel et al., Google Magenta | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [Medley-solos-DB](https://zenodo.org/records/3464194) | Vincent Lostanlen, Carmine-Emanuele Cella et al. | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

## Fonts
[Geist and Geist Mono](https://github.com/vercel/geist-font) by Vercel, in [`app/assets/fonts`](app/assets/fonts), under the [SIL Open Font License 1.1](app/assets/fonts/Geist-OFL.txt). They are bundled with the app.

## Libraries bundled with the app
The packaged app contains the Flutter runtime and a Python engine built with PyInstaller. These libraries keep their own licences.

| Library | Licence |
|---|---|
| [Flutter](https://flutter.dev/) engine and framework, [http](https://pub.dev/packages/http) | BSD-3-Clause |
| [lucide_icons_flutter](https://pub.dev/packages/lucide_icons_flutter) / [Lucide](https://lucide.dev/) icons | MIT / ISC |
| [Python](https://www.python.org/) runtime | PSF License 2.0 |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [ONNX Runtime](https://onnxruntime.ai/) | MIT |
| [Hugging Face Tokenizers](https://github.com/huggingface/tokenizers) | Apache-2.0 |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT |
| [FastAPI](https://fastapi.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/) | MIT |
| [Starlette](https://www.starlette.io/), [Uvicorn](https://www.uvicorn.org/) | BSD-3-Clause |
| [py-ptsl](https://github.com/iluvcapra/py-ptsl) | BSD-3-Clause |
| [gRPC](https://grpc.io/) (grpcio) | Apache-2.0 |
| [Protocol Buffers](https://protobuf.dev/) | BSD-3-Clause |
| [python-soundfile](https://github.com/bastibe/python-soundfile) | BSD-3-Clause |
| [libsndfile](https://libsndfile.github.io/libsndfile/) (bundled with python-soundfile) | LGPL-2.1-or-later |
| [python-soxr](https://github.com/dofuuz/python-soxr) with [libsoxr](https://sourceforge.net/projects/soxr/) | LGPL-2.1-or-later |
| [PyInstaller](https://pyinstaller.org/) bootloader | GPL-2.0 with bootloader exception |

**LGPL libraries:** neither is modified, and both can be replaced with your own builds of compatible versions. Their source code is available from the links above.
- libsndfile ships as a separate shared library in the app's `engine` folder.
- libsoxr is built into python-soxr's extension module (`soxr/soxr_ext`), which is itself a separate file there.

The full licence texts are included in the source distributions of these packages, and in the [Flutter](https://github.com/flutter/flutter/blob/master/LICENSE) and [Python](https://docs.python.org/3/license.html) projects.

## Trademarks
Pro Tools, AudioSuite and Avid are trademarks of Avid Technology, Inc. TrackMate is not affiliated with or endorsed by Avid.
