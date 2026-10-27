"""Knowledge base: kb/mix_naming.json plus the user's own aliases (saved corrections).

Lookup tables are keyed by the same normalisation the track names go through
(`names.tokenize`), so a KB alias and a file name match exactly when they spell the same
tokens.
"""
from __future__ import annotations

import json
import pathlib
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from .names import tokenize


def norm(text: str) -> str:
    return " ".join(t.text for t in tokenize(unicodedata.normalize("NFKC", text)))


@dataclass(frozen=True)
class Instrument:
    id: str
    canonical: str
    category: str
    generic: bool
    parent: str | None


@dataclass(frozen=True)
class Modifier:
    group: str
    canonical: str


@dataclass(frozen=True)
class Entry:
    """One searchable spelling of an instrument (used by layers B and C)."""
    text: str
    inst: str
    kind: str   # canonical | alias | abbrev | zh | ja | user
    lang: str   # en | zh | ja | user


class KnowledgeBase:
    def __init__(self, kb_path: pathlib.Path, user_aliases_path: pathlib.Path | None = None):
        self.path = kb_path
        self.user_aliases_path = user_aliases_path
        raw = json.loads(kb_path.read_text(encoding="utf-8"))
        self.version = raw.get("schema_version", "?")
        self.categories: dict[str, dict] = {}
        self.instruments: dict[str, Instrument] = {}
        self.phrases: dict[str, set[str]] = defaultdict(set)   # whole-token phrases (canonical, aliases)
        self.abbrevs: dict[str, set[str]] = defaultdict(set)   # single exact tokens
        self.cjk: dict[str, set[str]] = defaultdict(set)       # substrings (zh, ja)
        self.entries: list[Entry] = []
        self._seen: set[tuple[str, str]] = set()
        for cat in raw["categories"]:
            self.categories[cat["id"]] = {k: v for k, v in cat.items() if k != "instruments"}
            for inst in cat["instruments"]:
                self.instruments[inst["id"]] = Instrument(
                    inst["id"], inst["canonical"], cat["id"], bool(inst.get("generic")), inst.get("parent"))
                self._add(inst["canonical"], inst["id"], "canonical", "en", self.phrases)
                for a in inst.get("aliases", []):
                    self._add(a, inst["id"], "alias", "en", self.phrases)
                for a in inst.get("abbreviations", []):
                    self._add(a, inst["id"], "abbrev", "en", self.abbrevs)
                for lang in ("zh", "ja"):
                    for a in inst.get(lang, []):
                        self._add(a, inst["id"], lang, lang, self.cjk)
        self.modifiers: dict[str, Modifier] = {}
        for group, spec in raw.get("modifiers", {}).items():
            for term in spec["terms"]:
                m = Modifier(group, term["canonical"])
                for a in [term["canonical"], *term.get("aliases", []), *term.get("zh", []), *term.get("ja", [])]:
                    self.modifiers.setdefault(norm(a), m)
        self.ambiguous = {t.strip() for a in raw.get("ambiguous_terms", []) for t in a["term"].split("/")}
        self._lock = threading.Lock()
        self.user_aliases: dict[str, str] = {}
        self._load_user_aliases()

    def _add(self, text: str, inst: str, kind: str, lang: str, table: dict[str, set[str]]) -> None:
        t = norm(text)
        if not t:
            return
        table[t].add(inst)
        if (t, inst) not in self._seen:
            self._seen.add((t, inst))
            self.entries.append(Entry(t, inst, kind, lang))

    # ------------------------------------------------------------- user aliases
    def _load_user_aliases(self) -> None:
        p = self.user_aliases_path
        if p and p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            self.user_aliases = {k: v for k, v in data.get("aliases", {}).items() if v in self.instruments}

    def add_user_alias(self, name: str, inst: str) -> str:
        """Store a correction; the next analysis matches it in layer A. Returns the key."""
        if inst not in self.instruments:
            raise KeyError(inst)
        key = norm(name)
        if not key:
            raise ValueError("empty name")
        with self._lock:
            self.user_aliases[key] = inst
            if self.user_aliases_path:
                self.user_aliases_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.user_aliases_path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"aliases": self.user_aliases}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
                tmp.replace(self.user_aliases_path)
        return key

    # ------------------------------------------------------------------ helpers
    def knows(self, text: str) -> bool:
        """True for a single normalised word that names an instrument or a modifier."""
        return (text in self.phrases or text in self.abbrevs or text in self.modifiers
                or text in self.cjk or text in self.user_aliases)

    def category_of(self, inst: str) -> str:
        return self.instruments[inst].category

    def label(self, inst: str) -> str:
        return self.instruments[inst].canonical

    def generic_of(self, category: str) -> str | None:
        return next((i.id for i in self.instruments.values() if i.category == category and i.generic), None)
