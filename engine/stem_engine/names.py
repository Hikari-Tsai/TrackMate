"""Track-name preprocessing (README: Recognition pipeline): clean-up, tokenisation, batch prefix/suffix removal
and detection of DAW default names.

Every token keeps its original spelling (`surface`) so that words the knowledge base does not
know can be kept verbatim when renaming.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

_AUDIO_EXT = re.compile(r"\.(wav|wave|aiff?|mp3|flac|m4a|ogg|caf)$", re.I)
# What Pro Tools appends to the end of exported/rendered file names, removed repeatedly:
#   take and clip numbers   "Vox_03", "Vox_03-01", "Kick-03_"
#   playlist / duplicates   "Vox.04_09", "Lead Vox.1", "Snare.dup1"
#   AudioSuite renders      "Gtr-TCEx_01", "Gtr DI-AudSt_01": "-<tag>" right before a take number
_TAIL_NUMBERS = [re.compile(p, re.I) for p in (r"\.dup\d+$", r"[_-]\d{2,3}_?$", r"\.\d{1,2}$")]
_AUDIOSUITE_TAG = re.compile(r"-([A-Za-z][A-Za-z0-9]{1,15})$")
_TEMPO = re.compile(r"\b\d{2,3}\s?bpm\b", re.I)
_KEY = re.compile(r"\b[a-g](?:#|b|♯|♭)?\s?(?:maj|min|major|minor)\b|\b[a-g](?:#|♯|♭)m\b", re.I)
_DATE = re.compile(r"\b(?:19|20)\d{6}\b")
_SEP = re.compile(r"[\s_\-.,+()\[\]{}【】「」『』（）/\\|:;#*＊~'\"!?&=]+")
_CJK = r"぀-ヿㇰ-ㇿ㐀-䶿一-鿿豈-﫿가-힯"
_SCRIPT_SPLIT = re.compile(rf"(?<=[{_CJK}])(?=[^{_CJK}])|(?<=[^{_CJK}])(?=[{_CJK}])")
# "SnareTop" -> "Snare Top", "SNRTop" -> "SNR Top"; "BGVs" and "OHs" stay whole.
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]{2,})")
_LETTER_DIGIT = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z]{2,})")
_IS_CJK = re.compile(rf"[{_CJK}]")

DAW_DEFAULT_WORDS = {"audio", "track", "untitled", "new", "aux", "inst", "instrument", "mono", "stereo",
                     "オーディオ", "トラック", "音軌", "音訊", "音频", "音轨", "軌道"}


@dataclass
class Token:
    text: str      # normalised (lower case) form used for matching
    surface: str   # as written in the file name
    joined: bool = False  # split out of a word by case or digits ("CVox" -> "C" + "Vox"), not by a separator

    @property
    def is_cjk(self) -> bool:
        return bool(_IS_CJK.search(self.text))

    @property
    def is_number(self) -> bool:
        return self.text.isdigit()


@dataclass
class PreparedName:
    original: str
    cleaned: str
    tokens: list[Token] = field(default_factory=list)
    daw_tail: str = ""  # what was removed from the end ("_04-01", "-TCEx_01")
    stripped_prefix: list[str] = field(default_factory=list)
    stripped_suffix: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.tokens)

    @property
    def is_daw_default(self) -> bool:
        words = [t.text for t in self.tokens if not t.is_number]
        return not self.tokens or (bool(words) and all(w in DAW_DEFAULT_WORDS for w in words))


def strip_daw_tail(s: str, is_known: Callable[[str], bool] = lambda text: False) -> tuple[str, str]:
    """Remove take/clip/playlist numbers and AudioSuite tags from the end of a name.
    A "-Tag" is treated as an AudioSuite tag only when a take number followed it and the
    knowledge base does not know the word ("Vox-Lead_01" keeps "Lead"). Returns (rest, removed)."""
    removed = ""
    after_number = False
    while True:
        for pat in _TAIL_NUMBERS:
            m = pat.search(s)
            if m and m.start() > 0:
                removed, s, after_number = m.group() + removed, s[:m.start()], True
                break
        else:
            m = _AUDIOSUITE_TAG.search(s)
            if m and m.start() > 0 and after_number and not is_known(m.group(1).lower()):
                removed, s, after_number = m.group() + removed, s[:m.start()], False
                continue
            return s, removed


def clean(name: str, is_known: Callable[[str], bool] = lambda text: False) -> tuple[str, str]:
    """Normalised name without extension, DAW tail, tempo, key and dates; plus the DAW tail."""
    s = unicodedata.normalize("NFKC", name).strip()
    s = s.rsplit("/", 1)[-1]
    s = _AUDIO_EXT.sub("", s)
    s, tail = strip_daw_tail(s, is_known)
    s = _TEMPO.sub(" ", s)
    s = _KEY.sub(" ", s)
    s = _DATE.sub(" ", s)
    return s.strip(), tail


def tokenize(s: str) -> list[Token]:
    out = []
    for part in _SEP.split(s):
        if not part:
            continue
        pieces = _LETTER_DIGIT.sub(" ", _CAMEL.sub(" ", _SCRIPT_SPLIT.sub(" ", part))).split()
        for piece in pieces:
            out.append(Token(text=piece.lower(), surface=piece, joined=len(pieces) > 1))
    return out


def prepare(name: str, is_known: Callable[[str], bool] = lambda text: False) -> PreparedName:
    c, tail = clean(name, is_known)
    return PreparedName(original=name, cleaned=c, tokens=tokenize(c), daw_tail=tail)


def _key(tok: Token) -> str:
    return "#" if tok.is_number else tok.text


def strip_common_affixes(names: list[PreparedName], min_batch: int = 3,
                         is_known: Callable[[str], bool] = lambda text: False) -> None:
    """Remove token prefixes/suffixes shared by every name in the batch (usually the song
    title, e.g. 'ai-kotoba_' ... '_Track1'). Numbers compare equal to any number, so
    'Track1' and 'Track2' count as the same suffix. Words the knowledge base knows (`is_known`)
    are never stripped, so a batch of 'Tom 1', 'Tom 2', 'Tom 3' keeps its 'Tom'. Every name
    keeps at least one token."""
    if len(names) < min_batch:
        return
    shortest = min(len(n.tokens) for n in names)

    def shared(pos: int) -> bool:
        first = names[0].tokens[pos]
        return len({_key(n.tokens[pos]) for n in names}) == 1 and not is_known(first.text)

    pre = 0
    while pre < shortest - 1 and shared(pre) and not names[0].tokens[pre].is_number:
        pre += 1
    suf = 0
    while suf < shortest - 1 - pre and shared(-1 - suf):
        suf += 1
    # A suffix made only of numbers is the instance number, not a shared label.
    if suf and all(names[0].tokens[-1 - i].is_number for i in range(suf)):
        suf = 0
    for n in names:
        n.stripped_prefix = [t.surface for t in n.tokens[:pre]]
        n.stripped_suffix = [t.surface for t in n.tokens[len(n.tokens) - suf:]] if suf else []
        n.tokens = n.tokens[pre:len(n.tokens) - suf]


def prepare_batch(names: list[str], is_known: Callable[[str], bool] = lambda text: False) -> list[PreparedName]:
    prepared = [prepare(n, is_known) for n in names]
    strip_common_affixes(prepared, is_known=is_known)
    return prepared
