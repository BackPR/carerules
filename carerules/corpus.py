"""Load the official rulebooks (one text file per state, pages separated by form feeds), normalize text for
matching, check quotes word for word, and search pages with BM25."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "text"
SOURCES = ROOT / "data" / "sources.json"

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−­-"), None)
_WORD = re.compile(r"[a-z0-9§]+")
# Texas prints a weight after each rule ("[Medium-High]"); it isn't part of the rule's words, so quotes may leave it out.
WEIGHT = re.compile(r"\[(?:low|medium|high)(?:[- ]?(?:low|medium|high))?\]", re.I)


def norm(text: str) -> str:
    """Lowercase, fold Unicode, drop hyphens (so a word split across a line matches) and Texas rule weights, keep only
    letters, digits and §."""
    text = WEIGHT.sub(" ", unicodedata.normalize("NFKC", text)).lower().translate(_DASHES)
    return " ".join(_WORD.findall(text))


@dataclass(frozen=True)
class Page:
    state: str
    number: int  # 1-based page number in the official PDF
    text: str


@lru_cache(maxsize=None)
def sources() -> dict[str, dict]:
    return {s["state"]: s for s in json.loads(SOURCES.read_text())} if SOURCES.exists() else {}


@lru_cache(maxsize=None)
def pages(state: str) -> tuple[Page, ...]:
    raw = (TEXT_DIR / f"{state}.txt").read_text(encoding="utf-8")
    return tuple(Page(state, i + 1, t) for i, t in enumerate(raw.split("\f")) if t.strip())


def states() -> list[str]:
    return sorted(p.stem for p in TEXT_DIR.glob("*.txt"))


def build_index(texts: list[tuple[int, str]]) -> tuple[str, tuple[tuple[int, int], ...], tuple[frozenset, frozenset]]:
    """Normalize numbered pages into one string with spaces removed ("9 – 13 years" must match "9-13 years"),
    plus (start offset, page number) for each page, plus where words start and end, so a quote must begin and end
    on whole words ("attended" never matches inside "unattended")."""
    parts, offsets, starts, ends, pos = [], [], set(), set(), 0
    for number, text in texts:
        offsets.append((pos, number))
        for w in norm(text).split():
            starts.add(pos)
            if w.startswith("§") and len(w) > 1:
                starts.add(pos + 1)  # "746.1601" may be quoted without its §
            pos += len(w)
            ends.add(pos)
            parts.append(w)
    return "".join(parts), tuple(offsets), (frozenset(starts), frozenset(ends))


@lru_cache(maxsize=None)
def _normed(state: str) -> tuple:
    return build_index([(p.number, p.text) for p in pages(state)])


MAX_GAP = 300  # normalized characters (about 60 words) a "..." may skip in the inspector
SHORT_SKIP = 120  # a "..." skip this short (about 20 words) may not drop a negation
NEGATION = {"not", "no", "never", "nor", "neither", "cannot", "t", "except", "unless", "without"}  # "t": don't, can't
BENCH_GAP = 3000  # the question benchmark (answer key and grading), as published: quotes there may skip down a table


def locate(index: tuple, quote: str, max_gap: int = MAX_GAP) -> int | None:
    m = match(index, quote, max_gap)
    return m[0] if m else None


def match(index: tuple, quote: str, max_gap: int = MAX_GAP) -> tuple[int, int, int] | None:
    """(page, start, end) where `quote` appears word for word in an index from build_index, or None.

    Matching ignores case, punctuation, hyphens, spaces and line breaks, but each fragment must start and end on
    whole words. A quote may skip text with "..." (or "…"): each fragment must then appear in order, with at most
    `max_gap` characters between fragments. Quotes shorter than 6 words, or made only of fragments under 4 words,
    are rejected as too thin to prove anything.
    """
    hay, offsets, (starts, ends) = index
    frags = [norm(f) for f in re.split(r"\.\.\.|…", quote or "")]
    frags = [f for f in frags if f]
    # Evidence has to carry the document's own words: 6+ words in all, with at least one fragment of 4+ words.
    # A bare table cell such as "3 years ... 15" could match almost anywhere, so it doesn't count.
    if not frags or sum(len(f.split()) for f in frags) < 6 or max(len(f.split()) for f in frags) < 4:
        return None
    frags = [f.replace(" ", "") for f in frags]

    def find(f: str, at: int) -> int:  # next whole-word occurrence of f at or after `at`
        i = hay.find(f, at)
        while i != -1 and not (i in starts and i + len(f) in ends):
            i = hay.find(f, i + 1)
        return i

    def flips(a: int, b: int) -> bool:  # a short "..." skip must not drop a "not" (it would reverse the rule)
        if b - a > SHORT_SKIP or max_gap > MAX_GAP:  # the benchmark (BENCH_GAP) keeps its published rules
            return False
        cuts = [j for j in range(a, b) if j in starts] + [b]
        return any(hay[x:y] in NEGATION for x, y in zip(cuts, cuts[1:]))

    start = find(frags[0], 0)
    while start != -1:
        pos, ok = start + len(frags[0]), True
        for f in frags[1:]:
            nxt = find(f, pos)
            if nxt == -1 or nxt - pos > max_gap or flips(pos, nxt):
                ok = False
                break
            pos = nxt + len(f)
        if ok:
            page = offsets[0][1] if offsets else 1
            for begin, number in offsets:
                if begin > start:
                    break
                page = number
            return page, start, pos
        start = find(frags[0], start + 1)
    return None


def match_loose(index: tuple, quote: str) -> tuple[tuple[int, int, int], str] | None:
    """Like match, but when a quote runs past what the document says (typically two table rows joined into one
    quote), keep the longest leading or trailing part that does appear word for word: at least 6 words and at least
    half the quote. Returns the match and the verified text, which is all that may be shown."""
    m = match(index, quote)
    if m:
        return m, quote
    words = str(quote or "").split()
    if "..." in quote or "…" in quote or len(words) < 7:
        return None
    for k in range(len(words) - 1, max(6, -(-len(words) // 2)) - 1, -1):
        for part in (" ".join(words[:k]), " ".join(words[-k:])):
            m = match(index, part)
            if m:
                return m, part.strip(" ,;:")
    return None


GUIDANCE_NAME = {"TX": "a Texas \"Technical Assistance\" box", "CA": "California's handbook (explanatory) text"}
GUIDANCE = {  # lines that open and close non-binding guidance inside a rulebook
    "TX": (re.compile(r"^technical assistance\b", re.I), re.compile(r"^§\s?746\.\d+\.")),
    "CA": (re.compile(r"^handbook begins here", re.I), re.compile(r"^handbook ends here", re.I)),
}


@lru_cache(maxsize=None)
def _lines(state: str) -> tuple[tuple[int, str], ...]:
    """(normalized start offset, line) for every line of the rulebook, aligned with _normed's offsets."""
    out, pos = [], 0
    for p in pages(state):
        for line in p.text.split("\n"):
            out.append((pos, line.strip()))
            pos += len(norm(line).replace(" ", ""))
    return tuple(out)


def is_guidance(state: str, start: int) -> bool:
    """True if the text at normalized offset `start` sits inside a guidance passage (Texas "Technical Assistance",
    California "Handbook" material): explanation, not a rule."""
    if state not in GUIDANCE:
        return False
    opener, closer = GUIDANCE[state]
    lines = _lines(state)
    lo, hi = 0, len(lines) - 1
    while lo < hi:  # last line starting at or before `start`
        mid = (lo + hi + 1) // 2
        if lines[mid][0] <= start:
            lo = mid
        else:
            hi = mid - 1
    for i in range(lo, max(-1, lo - 400), -1):
        text = lines[i][1]
        if closer.search(text):
            return False
        if opener.search(text):
            return True
    return False


def find_rule(state: str, quote: str) -> tuple[int, str, bool] | None:
    """(page, verified text, is_guidance) for a rule quote, allowing the loose match above."""
    got = match_loose(_normed(state), quote)
    if not got:
        return None
    (page, start, _), text = got
    return page, text, is_guidance(state, start)


def find_row(state: str, quote: str, page: int) -> tuple[int, str, bool] | None:
    """A short table row ("0 – 11 months 4") is too thin to prove anything anywhere in a rulebook, but it does prove
    itself on the page of the rule it belongs to: whole words, at least 3, with a number, on `page` or the next page.
    Returns (page, row, is_guidance) like find_rule."""
    words = norm(quote).split()
    if len(words) < 3 or not any(w.isdigit() for w in words):
        return None
    hay, offsets, (starts, ends) = _normed(state)
    bounds = [b for b, n in offsets if n in (page, page + 1)]
    if not bounds:
        return None
    lo = bounds[0]
    after = [b for b, n in offsets if n > page + 1]
    hi = after[0] if after else len(hay)
    f = "".join(words)
    i = hay.find(f, lo)
    while i != -1 and i + len(f) <= hi:
        if i in starts and i + len(f) in ends:
            found = max(n for b, n in offsets if b <= i)
            return found, quote.strip(), is_guidance(state, i)
        i = hay.find(f, i + 1)
    return None


def find_quote(state: str, quote: str, max_gap: int = MAX_GAP) -> int | None:
    """Return the PDF page where `quote` appears word for word in the state's rulebook, or None (see locate)."""
    return locate(_normed(state), quote, max_gap)


class Index:
    """BM25 over pages of one or more rulebooks."""

    def __init__(self, states_: list[str] | None = None, k1: float = 1.2, b: float = 0.75):
        self.docs = [p for s in (states_ or states()) for p in pages(s)]
        self.toks = [norm(p.text).split() for p in self.docs]
        self.tf = [Counter(t) for t in self.toks]
        self.avg = sum(map(len, self.toks)) / max(1, len(self.toks))
        df = Counter(w for t in self.tf for w in t)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, state: str | None = None, k: int = 5) -> list[tuple[float, Page]]:
        q = [w for w in norm(query).split() if w in self.idf]
        scored = []
        for i, p in enumerate(self.docs):
            if state and p.state != state:
                continue
            tf, dl, s = self.tf[i], len(self.toks[i]), 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            if s > 0:
                scored.append((s, p))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


def page_url(state: str, page: int) -> str:
    """Link to the page in the official PDF; for Word or web sources (no fixed pages), the source itself."""
    src = sources().get(state, {})
    if not src.get("url"):
        return ""
    return f"{src['url']}#page={page}" if src.get("format", "pdf") == "pdf" else src["url"]


def is_pdf(state: str) -> bool:
    return sources().get(state, {}).get("format", "pdf") == "pdf"
