"""Layers A (dictionary) and B (fuzzy spelling) (README: Recognition pipeline), plus the parse of a name into
instrument + modifiers + number + unknown words.

Layer A rules (kb/mix_naming.json "matching_rules"):
- user aliases first, then the longest whole-token phrase; abbreviations only as a whole token;
  Chinese/Japanese terms as substrings, longest first; a token is used by one match only
- a term that is also a modifier ("room", "dbl", "strum"...) or listed in ambiguous_terms is
  "soft": it counts as an instrument only when no other instrument word is present
- a specific instrument beats a generic one of the same category; two categories -> ambiguous
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .config import Thresholds
from .kb import KnowledgeBase, Modifier
from .names import PreparedName

MAX_PHRASE = 4
# Ambiguous words that are never an instrument on their own (kb ambiguous_terms "resolution").
NEVER_ALONE = {"lead", "琴"}


@dataclass
class Span:
    start: int
    end: int            # exclusive, token positions
    text: str
    insts: set[str]
    soft: bool = False
    user: bool = False


@dataclass(frozen=True)
class ModHit:
    group: str
    canonical: str
    surface: str

    # Placement words are written the standard way ("left" -> "L"); the rest keep the
    # spelling used in the session ("Fuzz" stays "Fuzz" instead of "Distorted").
    CANONICAL_GROUPS = ("position_channel", "mic_position")

    @property
    def display(self) -> str:
        if self.group in self.CANONICAL_GROUPS or not self.surface.isascii():
            return self.canonical
        return self.surface if not self.surface.islower() else self.surface.capitalize()


@dataclass
class Parse:
    spans: list[Span] = field(default_factory=list)
    modifiers: list[ModHit] = field(default_factory=list)
    number: str | None = None
    unknown: list[str] = field(default_factory=list)     # surfaces of words nothing matched
    instrument: str | None = None                        # A-layer decision
    ambiguous: list[str] = field(default_factory=list)   # A-layer candidates when undecided


def _cjk_terms_in(text: str, table: dict[str, set[str]]) -> list[tuple[int, int, str]]:
    """Longest-first, non-overlapping substring matches of `table` keys in `text`."""
    found: list[tuple[int, int, str]] = []
    taken = [False] * len(text)
    for term in sorted((t for t in table if t in text), key=len, reverse=True):
        if len(term) == 1 and term != text:
            continue  # single characters (鼓, 琴) only when they are the whole token
        for m in re.finditer(re.escape(term), text):
            a, b = m.span()
            if not any(taken[a:b]):
                taken[a:b] = [True] * (b - a)
                found.append((a, b, term))
    return sorted(found)


def parse(name: PreparedName, kb: KnowledgeBase) -> Parse:
    toks = name.tokens
    used = [False] * len(toks)
    out = Parse()

    def soft(text: str) -> bool:
        return text in kb.modifiers or text in kb.ambiguous

    # 1. Latin phrases, longest first (user aliases win at each length).
    for n in range(min(MAX_PHRASE, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            window = toks[i:i + n]
            if any(used[i:i + n]) or any(t.is_cjk for t in window):
                continue
            text = " ".join(t.text for t in window)
            if text in kb.user_aliases:
                span = Span(i, i + n, text, {kb.user_aliases[text]}, user=True)
            elif text in kb.phrases or (n == 1 and text in kb.abbrevs):
                insts = set(kb.phrases.get(text, set())) | (kb.abbrevs.get(text, set()) if n == 1 else set())
                # One-letter codes ("v" for vocal) count only when they are the whole name;
                # in "Song Final v3" the v is a version.
                if len(text) == 1 and (window[0].joined or any(not t.is_number for j, t in enumerate(toks) if j != i)):
                    continue
                span = Span(i, i + n, text, insts, soft=soft(text))
            else:
                continue
            out.spans.append(span)
            used[i:i + n] = [True] * n

    # 2. Chinese / Japanese substrings; what is left of the token may still be a modifier (左, 右).
    cjk_rest: dict[int, str] = {}
    for i, t in enumerate(toks):
        if used[i] or not t.is_cjk:
            continue
        if t.text in kb.user_aliases:
            out.spans.append(Span(i, i + 1, t.text, {kb.user_aliases[t.text]}, user=True))
            used[i] = True
            continue
        hits = _cjk_terms_in(t.text, kb.cjk)
        rest = t.text
        for a, b, term in hits:
            out.spans.append(Span(i, i + 1, term, set(kb.cjk[term]), soft=soft(term)))
            rest = rest.replace(term, " ")
        if hits:
            used[i] = True
            cjk_rest[i] = rest

    # 3. Modifiers among the remaining tokens (longest phrase first), then the instance number.
    mods: list[tuple[int, ModHit]] = []
    for n in range(3, 0, -1):
        for i in range(len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            text = " ".join(t.text for t in toks[i:i + n])
            # A lone letter cut out of a word ("C" from "CVox") is not a placement word.
            if n == 1 and len(text) == 1 and toks[i].joined:
                continue
            if text in kb.modifiers:
                mods.append((i, _hit(kb.modifiers[text], " ".join(t.surface for t in toks[i:i + n]))))
                used[i:i + n] = [True] * n
    for i, rest in cjk_rest.items():
        for piece in rest.split():
            for a, b, term in _cjk_terms_in(piece, {k: set() for k in kb.modifiers}):
                mods.append((i, _hit(kb.modifiers[term], term)))
    numbers = [i for i, t in enumerate(toks) if not used[i] and t.is_number]
    if numbers:
        out.number = toks[numbers[-1]].text.lstrip("0") or "0"
        used[numbers[-1]] = True
    out.unknown = [t.surface for i, t in enumerate(toks) if not used[i]]

    _resolve(out, mods, kb)
    return out


def _hit(m: Modifier, surface: str) -> ModHit:
    return ModHit(m.group, m.canonical, surface)


def _resolve(out: Parse, mods: list[tuple[int, ModHit]], kb: KnowledgeBase) -> None:
    spans = [s for s in out.spans if s.text not in NEVER_ALONE]
    hard = [s for s in spans if not s.soft or s.user]
    words = {s.text for s in out.spans} | {m.canonical.lower() for _, m in mods}

    # "chorus" / "cho" next to a vocal word means backing vocals (kb ambiguous_terms).
    if words & {"chorus", "cho", "コーラス"} and any(kb.category_of(i) == "lead_vocals" for s in hard for i in s.insts):
        hard = [s for s in hard if not any(kb.category_of(i) == "lead_vocals" for i in s.insts)]
        hard.append(Span(0, 0, "chorus", {"backing_vocal"}))
    # "mmm" alone is the MMM minus-one deliverable; next to a vocal word it is humming.
    if "mmm" in words and any(kb.category_of(i) in ("lead_vocals", "backing_vocals") for s in hard for i in s.insts):
        hard = [s for s in hard if s.text != "mmm" and
                not any(kb.category_of(i) in ("lead_vocals", "backing_vocals") for i in s.insts)]
        hard.append(Span(0, 0, "mmm", {"oohs_aahs"}))

    chosen = hard or [s for s in spans if s.soft]
    if hard:
        # Soft words next to a real instrument act as modifiers ("Piano Room", "Vox Dbl").
        for s in out.spans:
            if s.soft and not s.user and s not in hard and s.text in kb.modifiers:
                mods.append((s.start, _hit(kb.modifiers[s.text], s.text)))
    elif len(chosen) > 1:
        chosen = chosen[:1]  # several soft words only: take the first, it is a weak guess anyway
    out.modifiers = [m for _, m in sorted(mods, key=lambda x: x[0])]

    insts: set[str] = set()
    for s in chosen:
        insts |= s.insts
    if not insts:
        return
    # Specific beats generic within a category; a child beats its parent.
    by_cat: dict[str, set[str]] = {}
    for i in insts:
        by_cat.setdefault(kb.category_of(i), set()).add(i)
    for cat, members in by_cat.items():
        specific = {i for i in members if not kb.instruments[i].generic}
        if specific:
            members &= specific
        parents = {kb.instruments[i].parent for i in members}
        by_cat[cat] = {i for i in members if i not in parents}
    first_seen = {}
    for s in sorted(chosen, key=lambda s: s.start):
        for i in sorted(s.insts):
            first_seen.setdefault(i, len(first_seen))
    remaining = sorted((i for members in by_cat.values() for i in members), key=lambda i: first_seen.get(i, 99))
    if len(remaining) == 1:
        out.instrument = remaining[0]
    else:
        out.ambiguous = remaining


@dataclass
class FuzzyHit:
    inst: str
    score: float
    margin: float
    query: str


_FUZZY_CACHE: dict[tuple[int, int], dict[str, set[str]]] = {}


def _fuzzy_owners(kb: KnowledgeBase, min_len: int) -> dict[str, set[str]]:
    key = (id(kb), min_len)
    if key not in _FUZZY_CACHE:
        owners: dict[str, set[str]] = {}
        for e in kb.entries:
            if e.lang == "en" and len(e.text) >= min_len:
                owners.setdefault(e.text, set()).add(e.inst)
        _FUZZY_CACHE[key] = owners
    return _FUZZY_CACHE[key]


def fuzzy_match(parsed: Parse, name: PreparedName, kb: KnowledgeBase, th: Thresholds) -> FuzzyHit | None:
    """Layer B: rapidfuzz WRatio over English spellings for the unknown words."""
    query = " ".join(w.lower() for w in parsed.unknown if not w.isdigit())
    if len(query.replace(" ", "")) < th.fuzzy_min_length:
        return None
    owners = _fuzzy_owners(kb, th.fuzzy_min_length)
    best: dict[str, float] = {}
    for text, score, _ in process.extract(query, list(owners), scorer=fuzz.WRatio, limit=25):
        # WRatio falls back to partial matching for strings of different length, which made
        # "ai kotoba" match "koto"; a spelling mistake keeps the length about the same.
        if not 0.75 <= len(text) / len(query) <= 1.33:
            continue
        for inst in owners[text]:
            best[inst] = max(best.get(inst, 0.0), score)
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    s1 = ranked[0][1]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if s1 >= th.fuzzy_min_score and s1 - s2 >= th.fuzzy_min_margin:
        return FuzzyHit(ranked[0][0], s1, s1 - s2, query)
    return None
