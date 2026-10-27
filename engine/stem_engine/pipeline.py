"""Recognition pipeline (README: Recognition pipeline): A dictionary -> B fuzzy -> C embedding -> D audio, merged
into one Top-1 plus up to five candidates per track.

Confidence: high = A; medium = B, C above the high threshold, or C and D agreeing on the
category; low = D only, or C and D disagreeing. Nothing found -> category "other", the
original name is kept and the track is flagged for review.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

from . import stereo
from .audio import AudioClassifier, DResult
from .config import DATA_DIR, Thresholds
from .embed import CResult, EmbeddingIndex
from .kb import KnowledgeBase
from .names import PreparedName, prepare_batch
from .textmatch import FuzzyHit, Parse, fuzzy_match, parse

_AUDIO_EXT = (".wav", ".wave", ".aif", ".aiff", ".mp3", ".flac", ".m4a", ".ogg", ".caf")
D_RERANK_WEIGHT = 0.15  # how much the audio category probability lifts a text candidate


def _load_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@dataclass
class Decision:
    instrument: str | None
    category: str
    stage: str          # A | B | C | C+D | D | none
    confidence: str     # high | medium | low | none


class Analyzer:
    def __init__(self, kb: KnowledgeBase, index: EmbeddingIndex | None = None,
                 audio: AudioClassifier | None = None, thresholds: Thresholds = Thresholds()):
        self.kb = kb
        self.index = index
        self.audio = audio
        self.th = thresholds
        self.categories = _load_json("categories.json")["categories"]
        self.palette = _load_json("pt_track_palette.json")["colors"]

    # ------------------------------------------------------------------ API
    def analyze(self, paths: list[str], audio: str = "auto", with_stereo: bool = True) -> list[dict]:
        """audio: 'none' (text layers only), 'auto' (D only where the text layers are unsure)
        or 'all'. File paths are only read for stereo analysis and the audio layer."""
        names = [pathlib.Path(p).name for p in paths]
        prepared = prepare_batch(names, is_known=self.kb.knows)
        parses = [parse(p, self.kb) for p in prepared]
        fuzzy: list[FuzzyHit | None] = [
            None if (r.instrument or r.ambiguous or p.is_daw_default) else fuzzy_match(r, p, self.kb, self.th)
            for p, r in zip(prepared, parses)]

        c_results: list[CResult | None] = [None] * len(paths)
        if self.index is not None:
            todo = [i for i, p in enumerate(prepared) if p.tokens and not p.is_daw_default]
            for i, res in zip(todo, self.index.query([prepared[i].text for i in todo])):
                c_results[i] = res

        out = []
        for i, path in enumerate(paths):
            p, r, fz, c = prepared[i], parses[i], fuzzy[i], c_results[i]
            settled = bool(r.instrument or fz or (c and self._c_high(c)))
            d = None
            if self.audio is not None and audio != "none" and (audio == "all" or not settled):
                if pathlib.Path(path).suffix.lower() in _AUDIO_EXT and pathlib.Path(path).exists():
                    d = self.audio.classify(path)
            decision = self._decide(r, fz, c, d)
            out.append(self._result(path, p, r, fz, c, d, decision, with_stereo))
        return out

    # ------------------------------------------------------------ decisions
    def _c_high(self, c: CResult) -> bool:
        return (c.s1 >= self.th.c_high and c.margin >= self.th.c_high_margin
                and c.none_margin > self.th.c_none_margin)

    def _c_zone(self, c: CResult | None) -> str:
        if c is None:
            return "none"
        if self._c_high(c):
            return "high"
        if c.s1 >= self.th.c_low and c.none_margin > self.th.c_none_margin:
            return "gray"
        return "low"

    def _d_usable(self, d: DResult | None) -> bool:
        return bool(d and not d.silent and d.best_category and d.best_prob >= self.th.d_min_prob)

    def _decide(self, r: Parse, fz: FuzzyHit | None, c: CResult | None, d: DResult | None) -> Decision:
        cat = self.kb.category_of
        if r.instrument:
            refined = self._refine(r, c)
            if refined:
                return Decision(refined, cat(refined), "A+C", "medium")
            return Decision(r.instrument, cat(r.instrument), "A", "high")
        if r.ambiguous:  # several categories in the name: let the audio pick, else first option
            if self._d_usable(d):
                for inst in r.ambiguous:
                    if cat(inst) == d.best_category:
                        return Decision(inst, cat(inst), "A+D", "medium")
            return Decision(r.ambiguous[0], cat(r.ambiguous[0]), "A", "low")
        if fz:
            return Decision(fz.inst, cat(fz.inst), "B", "medium")
        zone = self._c_zone(c)
        if zone == "high":
            return Decision(c.top[0][0], cat(c.top[0][0]), "C", "medium")
        if zone == "gray":
            top = c.top[0][0]
            if self._d_usable(d):
                if cat(top) == d.best_category:
                    return Decision(top, cat(top), "C+D", "medium")
                for inst, _ in c.top:
                    if cat(inst) == d.best_category:
                        return Decision(inst, cat(inst), "C+D", "low")
                return self._from_audio(d)
            return Decision(top, cat(top), "C", "low")
        if self._d_usable(d):
            return self._from_audio(d)
        return Decision(None, "other", "none", "none")

    def _refine(self, r: Parse, c: CResult | None) -> str | None:
        """The dictionary often finds only the family word ("Synthesized Bass" -> bass,
        "Main Singer" -> vocal) while the other words say which member it is. When the name has
        such extra words and the embedding's best match is a more specific instrument of the
        same family, take that one."""
        if c is None or not (r.unknown or r.modifiers) or self._c_zone(c) not in ("high", "gray"):
            return None
        a, top = r.instrument, c.top[0][0]
        inst = self.kb.instruments
        if top == a or inst[top].category != inst[a].category:
            return None
        return top if inst[a].generic or inst[top].parent == a else None

    def _from_audio(self, d: DResult) -> Decision:
        inst = d.best_instrument or self.categories[d.best_category]["representative"]
        return Decision(inst, d.best_category, "D", "low")

    # ---------------------------------------------------------------- output
    def _name(self, p: PreparedName, r: Parse, decision: Decision, keep_unknown: bool = False) -> str:
        """Standard name + modifiers + instance number. Words nothing recognised and the DAW
        tail ("_04-01", "-TCEx_01") are dropped by default; with keep_unknown they are kept
        verbatim (the front end lets the user choose)."""
        tail = p.daw_tail.lstrip("_-. ")
        if decision.instrument is None:
            # Nothing recognised: keep the name, only without the DAW tail by default.
            return pathlib.Path(p.original).stem if keep_unknown else (p.cleaned or pathlib.Path(p.original).stem)
        label = self.kb.label(decision.instrument)
        parts = [label]
        label_words = {w.lower() for w in label.split()}
        for m in r.modifiers:
            if m.display.lower() not in label_words and m.display not in parts:
                parts.append(m.display)
        if keep_unknown and decision.stage == "A":
            parts += r.unknown
        if r.number and not p.is_daw_default:  # "Audio 7": the 7 is the DAW's counter, not an instance
            parts.append(r.number)
        if keep_unknown and tail:
            parts.append(tail)
        return " ".join(parts)

    def _candidates(self, decision: Decision, r: Parse, c: CResult | None, d: DResult | None) -> list[dict]:
        scored: dict[str, tuple[float, str]] = {}

        def add(inst: str | None, score: float, source: str) -> None:
            if inst and inst in self.kb.instruments and inst not in scored:
                scored[inst] = (round(float(score), 4), source)

        if decision.instrument:
            add(decision.instrument, self._decision_score(decision, c, d), decision.stage)
        for inst in r.ambiguous:
            add(inst, 0.9, "A")
        if c:
            dcat = d.categories if d and not d.silent else {}
            reranked = sorted(c.top, key=lambda t: -(t[1] + D_RERANK_WEIGHT * dcat.get(self.kb.category_of(t[0]), 0.0)))
            for inst, s in reranked:
                add(inst, s, "C")
        if d and not d.silent:
            for key, prob in d.ranking:
                add(self._d_instrument(key), prob, "D")
        return [{"instrument": i, "label": self.kb.label(i), "category": self.kb.category_of(i),
                 "score": s, "source": src} for i, (s, src) in list(scored.items())[:5]]

    @staticmethod
    def _decision_score(decision: Decision, c: CResult | None, d: DResult | None) -> float:
        if decision.stage in ("A", "B", "A+D"):
            return 1.0
        c_scores = dict(c.top) if c else {}
        if decision.instrument in c_scores:
            return c_scores[decision.instrument]
        return d.best_prob if d else 0.0

    def _d_instrument(self, key: str) -> str | None:
        """Instrument a D-layer class stands for (category representative when generic)."""
        idx = self.audio.classes.index(key)
        inst = self.audio.class_instrument[idx] or None
        cat = self.audio.class_category[idx]
        return inst or (self.categories[cat]["representative"] if cat else None)

    def _result(self, path: str, p: PreparedName, r: Parse, fz, c, d, decision: Decision, with_stereo: bool) -> dict:
        cat = self.categories.get(decision.category, self.categories["other"])
        color_index = cat["color_index"]
        res = {
            "file": path,
            "original_name": pathlib.Path(path).stem,
            "proposed_name": self._name(p, r, decision),
            "proposed_name_keep": self._name(p, r, decision, keep_unknown=True),
            "unknown_words": r.unknown if decision.stage == "A" else [],
            "daw_tail": p.daw_tail,
            "instrument": decision.instrument,
            "category": decision.category,
            "category_label": self.kb.categories.get(decision.category, {}).get("name", "Other"),
            "color_index": color_index,
            "color": self.palette[color_index - 1],
            "folder": cat["folder"],
            "confidence": decision.confidence,
            "stage": decision.stage,
            "needs_review": decision.confidence in ("low", "none"),
            "candidates": self._candidates(decision, r, c, d),
            "modifiers": [m.display for m in r.modifiers],
            "number": r.number,
            "layers": {
                "prepared": p.text,
                "stripped": {"prefix": p.stripped_prefix, "suffix": p.stripped_suffix},
                "daw_default": p.is_daw_default,
                "fuzzy": fz and {"instrument": fz.inst, "score": fz.score, "margin": fz.margin},
                "embedding": c and {"top": c.top, "s1": round(c.s1, 4), "margin": round(c.margin, 4),
                                    "none_score": round(c.none_score, 4), "zone": self._c_zone(c)},
                "audio": d and {"best_category": d.best_category, "best_prob": round(d.best_prob, 4),
                                "ranking": [(k, round(v, 4)) for k, v in d.ranking[:5]],
                                "segments": d.segments, "silent": d.silent},
            },
        }
        if with_stereo and pathlib.Path(path).exists():
            try:
                res["stereo"] = stereo.analyze_file(path)
            except Exception as exc:  # unreadable file: report, keep the name result
                res["stereo"] = {"error": f"{type(exc).__name__}: {exc}"}
        return res
