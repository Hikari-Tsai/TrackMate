"""Zero-shot instrument recognition on public datasets.

Models
  pe-av-small   Meta PE-AV (audio <-> text, SigLIP-style logits = a.t * scale + bias)
  laion-clap    laion/larger_clap_general (cosine similarity; larger_clap_music gives
                near-identical audio embeddings for every clip, see REPORT)

Label spaces
  native   the dataset's own classes, described by text prompts
  family10 10 instrument families (sfx, woodwinds, brass, bass, strings, synth, drums,
           vocal, guitar, keys); dataset classes are mapped onto them and classes with
           no counterpart are excluded

Audio embeddings are cached per model/dataset under cache/, so prompt changes only
re-run the cheap text side.

Usage: python eval_instruments.py --dataset nsynth --models pe-av-small,laion-clap
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import time

import numpy as np
import soundfile as sf
import soxr

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "datasets"
CACHE = HERE / "cache"
OUT = HERE / "results"


TEMPLATES = ["the sound of {}", "a recording of {}", "{}", "a single note played on {}", "solo {}"]

# Text descriptions per class; several synonyms are averaged into one class prototype.
DESCRIPTIONS = {
    "nsynth": {
        "bass": ["a bass", "a bass guitar", "a synth bass"],
        "brass": ["a brass instrument", "a trumpet", "a trombone", "a french horn"],
        "flute": ["a flute", "a pan flute", "a recorder"],
        "guitar": ["a guitar", "an acoustic guitar", "an electric guitar"],
        "keyboard": ["a keyboard", "a piano", "an electric piano"],
        "mallet": ["mallet percussion", "a marimba", "a xylophone", "a vibraphone"],
        "organ": ["an organ", "a hammond organ", "a pipe organ"],
        "reed": ["a reed instrument", "a saxophone", "a clarinet", "an oboe"],
        "string": ["a bowed string instrument", "a violin", "a cello"],
        "vocal": ["a singing voice", "a singer", "a choir"],
    },
    "medley_solos": {
        "clarinet": ["a clarinet", "a bass clarinet"],
        "distorted electric guitar": ["a distorted electric guitar", "an overdriven electric guitar"],
        "female singer": ["a female singer", "a woman singing", "a female voice"],
        "flute": ["a flute", "a concert flute"],
        "piano": ["a piano", "a grand piano"],
        "tenor saxophone": ["a tenor saxophone", "a saxophone"],
        "trumpet": ["a trumpet", "a muted trumpet"],
        "violin": ["a violin", "a solo violin"],
    },
    "family10": {
        "sfx": ["a sound effect", "noise"],
        "woodwinds": ["a woodwind instrument", "a flute", "a saxophone", "a clarinet"],
        "brass": ["a brass instrument", "a trumpet", "a trombone"],
        "bass": ["a bass", "a bass guitar", "a synth bass"],
        "strings": ["a string section", "a violin", "a cello"],
        "synth": ["a synthesizer", "a synth lead", "a synth pad"],
        "drums": ["drums", "a drum kit", "percussion"],
        "vocal": ["a singing voice", "a singer", "vocals"],
        "guitar": ["a guitar", "an acoustic guitar", "an electric guitar"],
        "keys": ["a piano", "a keyboard", "an organ"],
    },
}

# dataset class -> family10 label (None = excluded from the family10 evaluation)
TO_FAMILY = {
    "nsynth": {"bass": "bass", "brass": "brass", "flute": "woodwinds", "guitar": "guitar", "keyboard": "keys",
               "mallet": None, "organ": "keys", "reed": "woodwinds", "string": "strings", "vocal": "vocal"},
    "medley_solos": {"clarinet": "woodwinds", "distorted electric guitar": "guitar", "female singer": "vocal",
                     "flute": "woodwinds", "piano": "keys", "tenor saxophone": "woodwinds",
                     "trumpet": "brass", "violin": "strings"},
}


# ----------------------------------------------------------------- datasets
def load_dataset(name: str) -> list[dict]:
    if name == "nsynth":
        root = DATA / "nsynth" / "nsynth-test"
        meta = json.loads((root / "examples.json").read_text())
        return [dict(id=k, path=str(root / "audio" / f"{k}.wav"), label=v["instrument_family_str"],
                     group=v["instrument_source_str"]) for k, v in sorted(meta.items())]
    if name == "medley_solos":
        # Official test split only. Files are named Medley-solos-DB_<subset>-<instrument_id>_<uuid4>.wav;
        # the archive layout is not documented, so locate them by name.
        import csv
        root = DATA / "medley_solos"
        wavs = {p.name: p for p in root.rglob("*.wav")}
        items = []
        with open(root / "Medley-solos-DB_metadata.csv") as f:
            for row in csv.DictReader(f):
                if row["subset"] != "test":
                    continue
                fname = f"Medley-solos-DB_{row['subset']}-{row['instrument_id']}_{row['uuid4']}.wav"
                if fname not in wavs:
                    raise FileNotFoundError(fname)
                items.append(dict(id=row["uuid4"], path=str(wavs[fname]), label=row["instrument"], group="test"))
        return items
    raise ValueError(name)


def read_mono(path: str, sr: int) -> np.ndarray:
    x, file_sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    return soxr.resample(x, file_sr, sr) if file_sr != sr else x


# ----------------------------------------------------------------- models
def device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


class PEAV:
    name, sr = "pe-av-small", 48000

    def __init__(self, model_id: str = "facebook/pe-av-small"):
        import torch
        from transformers import AutoFeatureExtractor, AutoTokenizer, PeAudioVideoModel
        self.torch, self.dev = torch, device()
        # transformers 5.20 rebuilds the timm video embedder with a different width than the
        # checkpoint. Only audio/text weights are used here, so tolerate mismatches that are
        # confined to the video branch and fail on anything else.
        model, info = PeAudioVideoModel.from_pretrained(model_id, ignore_mismatched_sizes=True,
                                                        output_loading_info=True)
        bad = [k for k in [*info.get("mismatched_keys", []), *info.get("missing_keys", [])]
               if not str(k[0] if isinstance(k, tuple) else k).startswith("video_model.")]
        if bad:
            raise RuntimeError(f"unexpected weight mismatches outside the video branch: {bad}")
        self.model = model.to(self.dev).eval()
        self.fe = AutoFeatureExtractor.from_pretrained(model_id)
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.name = model_id.split("/")[-1]

    def audio(self, waves: list[np.ndarray]) -> np.ndarray:
        with self.torch.no_grad():
            b = self.fe(waves, sampling_rate=self.sr, return_tensors="pt")
            e = self.model.get_audio_embeds(b["input_values"].to(self.dev), b["padding_mask"].to(self.dev))
        return e.float().cpu().numpy()

    def text(self, texts: list[str]) -> np.ndarray:
        with self.torch.no_grad():
            t = self.tok(texts, padding=True, return_tensors="pt").to(self.dev)
            # Same path as PeAudioVideoModel.forward; get_text_audio_embeds() is broken in
            # transformers 5.20 (it calls a method PeAudioModel does not have).
            out = self.model.text_model(input_ids=t["input_ids"], attention_mask=t["attention_mask"],
                                        output_hidden_states=True)
            e = self.model.audio_model.text_audio_head(out.hidden_states[-1][:, 0])
        return e.float().cpu().numpy()

    def score(self, a: np.ndarray, t: np.ndarray) -> np.ndarray:
        # Model's own logits; scale > 0 and bias is shared, so ranking equals the raw dot product.
        return a @ t.T


class LaionCLAP:
    name, sr = "laion-clap-general", 48000

    def __init__(self, model_id: str = "laion/larger_clap_general"):
        import torch
        from transformers import ClapModel, ClapProcessor
        self.torch, self.dev = torch, device()
        self.model = ClapModel.from_pretrained(model_id).to(self.dev).eval()
        self.proc = ClapProcessor.from_pretrained(model_id)

    def audio(self, waves: list[np.ndarray]) -> np.ndarray:
        with self.torch.no_grad():
            b = self.proc(audio=waves, sampling_rate=self.sr, return_tensors="pt").to(self.dev)
            e = self.model.get_audio_features(**b)
        e = getattr(e, "pooler_output", e)
        return e.float().cpu().numpy()

    def text(self, texts: list[str]) -> np.ndarray:
        with self.torch.no_grad():
            t = self.proc(text=texts, padding=True, return_tensors="pt").to(self.dev)
            e = self.model.get_text_features(**t)
        e = getattr(e, "pooler_output", e)
        return e.float().cpu().numpy()

    def score(self, a: np.ndarray, t: np.ndarray) -> np.ndarray:
        a = a / np.linalg.norm(a, axis=1, keepdims=True)
        t = t / np.linalg.norm(t, axis=1, keepdims=True)
        return a @ t.T


# ----------------------------------------------------------------- evaluation
def metrics(y_true: list[str], scores: np.ndarray, classes: list[str], groups: list[str]) -> dict:
    order = np.argsort(-scores, axis=1)
    pred = [classes[i] for i in order[:, 0]]
    n = len(y_true)
    top3 = sum(t in [classes[i] for i in row[:3]] for t, row in zip(y_true, order))
    per_class = {}
    for c in sorted(set(y_true)):
        idx = [i for i, t in enumerate(y_true) if t == c]
        tp = sum(pred[i] == c for i in idx)
        predicted = sum(p == c for p in pred)
        rec = tp / len(idx)
        prec = tp / predicted if predicted else 0.0
        per_class[c] = dict(n=len(idx), recall=round(rec, 4), precision=round(prec, 4),
                            f1=round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0)
    by_group = {}
    for g in sorted(set(groups)):
        idx = [i for i, x in enumerate(groups) if x == g]
        by_group[g] = dict(n=len(idx), accuracy=round(sum(pred[i] == y_true[i] for i in idx) / len(idx), 4))
    confusion = collections.Counter((t, p) for t, p in zip(y_true, pred) if t != p).most_common(8)
    return dict(n=n,
                accuracy=round(sum(p == t for p, t in zip(pred, y_true)) / n, 4),
                balanced_accuracy=round(float(np.mean([v["recall"] for v in per_class.values()])), 4),
                macro_f1=round(float(np.mean([v["f1"] for v in per_class.values()])), 4),
                recall_at_3=round(top3 / n, 4),
                per_class=per_class, by_source=by_group,
                top_confusions=[f"{t}->{p}: {c}" for (t, p), c in confusion])


def class_prototypes(model, space: str) -> tuple[list[str], np.ndarray]:
    classes = list(DESCRIPTIONS[space])
    protos = []
    for c in classes:
        prompts = [tpl.format(d) for d in DESCRIPTIONS[space][c] for tpl in TEMPLATES]
        protos.append(model.text(prompts).mean(axis=0))
    return classes, np.stack(protos)


def embed_audio(model, dataset: str, items: list[dict], batch: int = 16) -> np.ndarray:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{model.name}_{dataset}.npy"
    if path.exists():
        return np.load(path)
    out = []
    t0 = time.perf_counter()
    for i in range(0, len(items), batch):
        out.append(model.audio([read_mono(it["path"], model.sr) for it in items[i:i + batch]]))
        if i % (batch * 20) == 0:
            print(f"  {model.name}: {i + batch}/{len(items)} ({time.perf_counter() - t0:.0f}s)", flush=True)
    emb = np.concatenate(out)
    np.save(path, emb)
    return emb


def run_zero_shot(model, dataset: str, items: list[dict]) -> dict:
    emb = embed_audio(model, dataset, items)
    res = {}
    classes, protos = class_prototypes(model, dataset)
    res["native"] = metrics([it["label"] for it in items], model.score(emb, protos), classes,
                            [it["group"] for it in items])
    keep = [i for i, it in enumerate(items) if TO_FAMILY[dataset][it["label"]]]
    classes, protos = class_prototypes(model, "family10")
    res["family10"] = metrics([TO_FAMILY[dataset][items[i]["label"]] for i in keep],
                             model.score(emb[keep], protos), classes, [items[i]["group"] for i in keep])
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="nsynth")
    ap.add_argument("--models", default="pe-av-small,laion-clap")
    args = ap.parse_args()
    items = load_dataset(args.dataset)
    OUT.mkdir(exist_ok=True)
    out_path = OUT / f"{args.dataset}.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    for key in args.models.split(","):
        t0 = time.perf_counter()
        model = PEAV() if key == "pe-av-small" else LaionCLAP()
        res = run_zero_shot(model, args.dataset, items)
        res["seconds"] = round(time.perf_counter() - t0, 1)
        results[key] = res
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        brief = {k: {m: v[m] for m in ("accuracy", "balanced_accuracy", "macro_f1", "recall_at_3") if m in v}
                 if isinstance(v, dict) and "accuracy" in v else v for k, v in res.items()}
        print(key, json.dumps(brief, ensure_ascii=False), flush=True)
        del model
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
