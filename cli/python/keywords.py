"""
Dictionary-free keyword extractor — Python port of the JS version in
public/lib/mdp-viewer.mjs (KeywordExtractor + detectStructuralTags).

Algorithm: N-gram (CJK 2~8) + ASCII tokens, scored by PMI cohesion x
min(left, right) Shannon entropy. Based on the "無詞典新詞發現" method
(see memory/reference_keyword_pdf.md for the authoritative reference).

Kept structurally identical to the JS implementation so Markdown+ documents
yield the same auto-keywords whether they are viewed in the HTML viewer,
queried from the MCP server, or hit through the HTTP API. If you change
parameters or scoring here, change them in mdp-viewer.mjs too.
"""
from __future__ import annotations

import math
import re

_KEYWORD_SENTENCE_SPLIT_RE = re.compile(
    r"[\s　，。!?！？；：、,.;:()\[\]【】"
    r"「」『』“”‘’《》<>/\\\n\r\t]+"
)
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+\-]*")
_ASCII_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+\-]*$")
_BLOCK_HEADER_LINE_RE = re.compile(r"^\s*-\s+\*\*#[a-z0-9][a-z0-9-]*\*\*.*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
_MERMAID_BLOCK_RE = re.compile(
    r"^[ \t]*```[ \t]*mermaid\b[ \t]*\r?\n([\s\S]*?)^[ \t]*```",
    re.MULTILINE,
)
_SVG_FENCE_RE = re.compile(r"^[ \t]*```[ \t]*svg\b", re.MULTILINE)
_MERMAID_DIAGRAM_ID_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)")


def _is_cjk(ch: str) -> bool:
    if not ch:
        return False
    c = ord(ch)
    return (
        0x4E00 <= c <= 0x9FFF
        or 0x3400 <= c <= 0x4DBF
        or 0xF900 <= c <= 0xFAFF
    )


def _entropy(counts: dict) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    ent = 0.0
    for v in counts.values():
        p = v / total
        ent -= p * math.log(p)
    return ent


def clean_text(text: str) -> str:
    """Strip markdown noise that should not contribute to N-gram statistics.
    Mirrors KeywordExtractor.cleanText in mdp-viewer.mjs."""
    s = str(text)
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"~~~[\s\S]*?~~~", " ", s)
    s = re.sub(r"`[^`]*`", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", s)
    s = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", s)
    s = _BLOCK_HEADER_LINE_RE.sub(" ", s)
    s = _HEADING_RE.sub(" ", s)
    s = re.sub(r"[*_>|]+", " ", s)
    return s


class KeywordExtractor:
    """Fits on the whole document, then scores candidates per-block."""

    def __init__(
        self,
        *,
        min_len: int = 2,
        max_len: int = 8,
        min_freq: int = 2,
        min_pmi: float = 1.0,
        min_entropy: float = 0.4,
        min_ascii_len: int = 3,
    ):
        self.min_len = min_len
        self.max_len = max_len
        self.min_freq = min_freq
        self.min_pmi = min_pmi
        self.min_entropy = min_entropy
        self.min_ascii_len = min_ascii_len
        self.ngram_freq: dict[str, int] = {}
        self.left_neighbors: dict[str, dict[str, int]] = {}
        self.right_neighbors: dict[str, dict[str, int]] = {}
        self.total_chars = 0

    def _inc(self, k: str) -> None:
        self.ngram_freq[k] = self.ngram_freq.get(k, 0) + 1

    def _add_neighbor(self, cand: str, left: str, right: str) -> None:
        lm = self.left_neighbors.setdefault(cand, {})
        rm = self.right_neighbors.setdefault(cand, {})
        lm[left] = lm.get(left, 0) + 1
        rm[right] = rm.get(right, 0) + 1

    def fit(self, text: str) -> "KeywordExtractor":
        cleaned = clean_text(text)
        for sent in _KEYWORD_SENTENCE_SPLIT_RE.split(cleaned):
            if len(sent) >= 2:
                self._scan_sentence(sent)
        return self

    def _scan_sentence(self, sent: str) -> None:
        arr = list(sent)
        n = len(arr)
        for i in range(n):
            if _is_cjk(arr[i]):
                self._inc(arr[i])
            self.total_chars += 1
        for i in range(n):
            if not _is_cjk(arr[i]):
                continue
            L = self.min_len
            while L <= self.max_len and i + L <= n:
                ok = True
                for k in range(L):
                    if not _is_cjk(arr[i + k]):
                        ok = False
                        break
                if not ok:
                    break
                cand = "".join(arr[i:i + L])
                self._inc(cand)
                left = arr[i - 1] if i > 0 else "<BOS>"
                right = arr[i + L] if i + L < n else "<EOS>"
                self._add_neighbor(cand, left, right)
                L += 1
        for m in _ASCII_TOKEN_RE.finditer(sent):
            tok = m.group(0)
            if len(tok) < self.min_ascii_len:
                continue
            self._inc(tok)
            start, end = m.start(), m.end()
            left = sent[start - 1] if start > 0 else "<BOS>"
            right = sent[end] if end < len(sent) else "<EOS>"
            self._add_neighbor(tok, left, right)

    def _prob(self, token: str) -> float:
        return self.ngram_freq.get(token, 0) / max(self.total_chars, 1)

    def cohesion(self, word: str) -> float:
        if _ASCII_WORD_RE.match(word):
            return math.log(max(self.ngram_freq.get(word, 1), 1)) + 1
        arr = list(word)
        if len(arr) < 2:
            return 0.0
        p_word = self._prob(word)
        if p_word <= 0:
            return 0.0
        min_pmi = math.inf
        for i in range(1, len(arr)):
            pl = self._prob("".join(arr[:i]))
            pr = self._prob("".join(arr[i:]))
            if pl <= 0 or pr <= 0:
                return 0.0
            pmi = math.log(p_word / (pl * pr))
            if pmi < min_pmi:
                min_pmi = pmi
        return 0.0 if min_pmi == math.inf else min_pmi

    def discover(self, *, top_k: int = 80) -> list[dict]:
        results: list[dict] = []
        for word, freq in self.ngram_freq.items():
            if freq < self.min_freq:
                continue
            is_ascii = bool(_ASCII_WORD_RE.match(word))
            if not is_ascii:
                arr_len = len(word)  # CJK 1 char = 1 code point in BMP/SMP relevant ranges
                if arr_len < self.min_len or arr_len > self.max_len:
                    continue
            else:
                if len(word) < self.min_ascii_len:
                    continue
            coh = self.cohesion(word)
            if coh < self.min_pmi:
                continue
            left_ent = _entropy(self.left_neighbors.get(word, {}))
            right_ent = _entropy(self.right_neighbors.get(word, {}))
            if left_ent < self.min_entropy or right_ent < self.min_entropy:
                continue
            score = freq * coh * min(left_ent, right_ent)
            results.append({"word": word, "freq": freq, "score": score})
        results.sort(key=lambda r: -r["score"])
        kept: list[dict] = []
        for r in results:
            suppress = False
            k = 0
            while k < len(kept):
                o = kept[k]
                if o["word"] == r["word"]:
                    k += 1
                    continue
                if o["word"].find(r["word"]) >= 0 and o["freq"] >= r["freq"] * 0.6:
                    suppress = True
                    break
                if (
                    r["word"].find(o["word"]) >= 0
                    and r["freq"] >= o["freq"] * 0.6
                    and len(r["word"]) > len(o["word"])
                ):
                    kept.pop(k)
                    continue
                k += 1
            if not suppress:
                kept.append(r)
            if len(kept) >= top_k:
                break
        return kept

    def keywords_for_block(
        self,
        block_text: str,
        candidates: list[dict],
        top_n: int = 5,
    ) -> list[str]:
        cleaned = clean_text(block_text)
        hits: list[dict] = []
        for c in candidates:
            w = c["word"]
            cnt = 0
            idx = 0
            while True:
                idx = cleaned.find(w, idx)
                if idx < 0:
                    break
                cnt += 1
                idx += len(w)
            if cnt > 0:
                hits.append({
                    "word": w,
                    "score": c["score"] * math.log(cnt + 1),
                })
        hits.sort(key=lambda h: -h["score"])
        out: list[str] = []
        for h in hits:
            skip = False
            for o in out:
                if o.find(h["word"]) >= 0 or h["word"].find(o) >= 0:
                    skip = True
                    break
            if not skip:
                out.append(h["word"])
            if len(out) >= top_n:
                break
        return out


# --- structural tag detector (port of detectStructuralTags) ---

def _extract_table_column_headers(body_text: str) -> list[str]:
    lines = body_text.split("\n")
    for i in range(len(lines) - 1):
        header_line = lines[i]
        sep_line = lines[i + 1] if i + 1 < len(lines) else ""
        if _TABLE_ROW_RE.match(header_line) and _TABLE_SEP_RE.match(sep_line):
            body = header_line.strip()
            if body.startswith("|"):
                body = body[1:]
            if body.endswith("|"):
                body = body[:-1]
            out: list[str] = []
            for raw in body.split("|"):
                cleaned = raw
                cleaned = re.sub(r"`[^`]*`", "", cleaned)
                cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
                cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
                cleaned = re.sub(r"^[\s—–-]+|[\s—–-]+$", "", cleaned).strip()
                if 1 <= len(cleaned) <= 24 and re.search(r"[A-Za-z一-鿿0-9]", cleaned):
                    out.append(cleaned)
            return out
    return []


def detect_structural_tags(body_text: str, block_type: str) -> list[str]:
    """Pull out non-prose signals — mermaid diagram type, svg fence, table headers.
    Mirrors detectStructuralTags in mdp-viewer.mjs."""
    tags: list[str] = []
    for mm in _MERMAID_BLOCK_RE.finditer(body_text):
        if "mermaid" not in tags:
            tags.append("mermaid")
        for raw_line in mm.group(1).split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("%%") or line.startswith("---"):
                continue
            id_m = _MERMAID_DIAGRAM_ID_RE.match(line)
            if id_m:
                dt = id_m.group(1)
                if dt != "title" and dt not in tags:
                    tags.append(dt)
            break
    if _SVG_FENCE_RE.search(body_text) and "svg" not in tags:
        tags.append("svg")
    if block_type in ("table", "targets"):
        for h in _extract_table_column_headers(body_text):
            if h not in tags:
                tags.append(h)
    return tags
