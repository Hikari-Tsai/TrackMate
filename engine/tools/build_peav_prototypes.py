"""Build the D-layer class prototypes with PE-AV's text encoder (PyTorch, offline).

The app ships only the audio encoder (ONNX), so the text side is computed here once:
each class prototype is the mean text embedding of its prompts x templates, the same recipe
as experiments/instrument_zeroshot (where PE-AV small scored 96 % on Medley-solos).

Output: stem_engine/data/peav_prototypes.npz with
  classes    [n]         class keys ("drums", "utility:click", "trap:full_mix", ...)
  categories [n]         KB category id, or "" for trap classes
  instruments[n]         instrument id the class stands for, or ""
  prototypes [n, 1024]   float32, not normalised (PE-AV logits use the raw dot product)

Run (needs the PyTorch model; transformers 5.20.2):
  uv run --no-project --python 3.12 --with numpy --with soundfile --with soxr --with librosa \
    --with onnxruntime --with "transformers==5.20.2" --with torch --with timm --with pillow \
    python tools/build_peav_prototypes.py
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "instrument_zeroshot"))
from eval_instruments import PEAV  # noqa: E402

OUT = HERE.parent / "stem_engine" / "data" / "peav_prototypes.npz"
TEMPLATES = ["the sound of {}", "a recording of {}", "{}", "solo {}"]

# class key -> (category, instrument, descriptions). Trap classes absorb audio that is not a
# single instrument; their prompts are specific on purpose (vague prompts such as "noise"
# pulled bass and keys notes away in the NSynth evaluation).
CLASSES = {
    "drums": ("drums", "drums", ["drums", "a drum kit", "a kick drum", "a snare drum", "cymbals and hi-hats"]),
    "percussion": ("percussion", "percussion", ["hand percussion", "a shaker", "a tambourine", "congas and bongos"]),
    "bass": ("bass", "bass", ["a bass guitar", "an electric bass playing a bass line", "a synth bass", "a double bass"]),
    "guitars": ("guitars", "guitar", ["an electric guitar", "an acoustic guitar", "a distorted electric guitar",
                                      "a strummed guitar"]),
    "keys": ("keys", "keys", ["a piano", "an electric piano", "an organ", "a keyboard"]),
    "synths": ("synths", "synth", ["a synthesizer", "a synth pad", "a synth lead", "an arpeggiated synthesizer"]),
    "strings": ("strings", "strings", ["a string section", "a violin", "a cello", "orchestral strings"]),
    "brass": ("brass", "brass", ["a brass section", "a trumpet", "a trombone", "a french horn"]),
    "woodwinds": ("woodwinds", "woodwinds", ["a flute", "a saxophone", "a clarinet", "a woodwind instrument"]),
    "lead_vocals": ("lead_vocals", "vocal", ["a singer", "a solo singing voice", "a lead vocal", "a person singing"]),
    "backing_vocals": ("backing_vocals", "backing_vocal", ["backing vocals", "a choir", "several singers harmonizing",
                                                           "background singers"]),
    "fx": ("fx", "sfx", ["a sound effect such as a riser or an impact", "a whoosh sound effect",
                         "a cinematic impact sound effect"]),
    "utility:click": ("utility", "click", ["a metronome click track", "a metronome ticking"]),
    "utility:mix": ("utility", "mix_print", ["a full song mix with many instruments", "a complete band playing a song"]),
    "trap:speech": ("", "", ["a person talking", "people speaking"]),
    "trap:noise": ("", "", ["background hiss and hum", "electrical noise"]),
}


def main() -> int:
    model = PEAV()
    keys, cats, insts, protos = [], [], [], []
    for key, (cat, inst, descs) in CLASSES.items():
        emb = model.text([t.format(d) for d in descs for t in TEMPLATES])
        keys.append(key)
        cats.append(cat)
        insts.append(inst)
        protos.append(emb.mean(axis=0))
        print(f"{key:16s} prompts={len(descs) * len(TEMPLATES):2d} norm={np.linalg.norm(protos[-1]):.3f}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez(OUT, classes=np.array(keys), categories=np.array(cats), instruments=np.array(insts),
             prototypes=np.stack(protos).astype(np.float32))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
