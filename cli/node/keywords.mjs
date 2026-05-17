// Dictionary-free keyword extractor — Node ESM port mirroring
// cli/python/keywords.py and public/lib/mdp-viewer.mjs (KeywordExtractor +
// detectStructuralTags).
//
// All three implementations must yield the same auto-keywords for the same
// source. Algorithm: N-gram (CJK 2-8) + ASCII tokens, scored by PMI cohesion
// x min(left, right) Shannon entropy ("無詞典新詞發現" method).
// If you change parameters or scoring here, change them in the other two too.

const KEYWORD_SENTENCE_SPLIT_RE = /[\s　，。!?！？；：、,.;:()\[\]【】「」『』""''《》<>\/\\\n\r\t]+/;
const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
const TABLE_SEP_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/;
const MERMAID_BLOCK_RE = /^[ \t]*```[ \t]*mermaid\b[ \t]*\r?\n([\s\S]*?)^[ \t]*```/gm;
const SVG_FENCE_RE = /^[ \t]*```[ \t]*svg\b/m;
const MERMAID_DIAGRAM_ID_RE = /^([A-Za-z][A-Za-z0-9-]*)/;

function isCJK(ch) {
  if (!ch) return false;
  const c = ch.codePointAt(0);
  return (c >= 0x4e00 && c <= 0x9fff) || (c >= 0x3400 && c <= 0x4dbf) || (c >= 0xf900 && c <= 0xfaff);
}

function entropyOfMap(map) {
  let total = 0;
  for (const v of map.values()) total += v;
  if (total === 0) return 0;
  let ent = 0;
  for (const v of map.values()) {
    const p = v / total;
    ent -= p * Math.log(p);
  }
  return ent;
}

export class KeywordExtractor {
  constructor(opts = {}) {
    this.minLen = opts.minLen ?? 2;
    this.maxLen = opts.maxLen ?? 8;
    this.minFreq = opts.minFreq ?? 2;
    this.minPmi = opts.minPmi ?? 1.0;
    this.minEntropy = opts.minEntropy ?? 0.4;
    this.minAsciiLen = opts.minAsciiLen ?? 3;
    this.ngramFreq = new Map();
    this.leftNeighbors = new Map();
    this.rightNeighbors = new Map();
    this.totalChars = 0;
  }
  _inc(k) { this.ngramFreq.set(k, (this.ngramFreq.get(k) || 0) + 1); }
  _addNeighbor(cand, left, right) {
    let lm = this.leftNeighbors.get(cand);
    if (!lm) { lm = new Map(); this.leftNeighbors.set(cand, lm); }
    let rm = this.rightNeighbors.get(cand);
    if (!rm) { rm = new Map(); this.rightNeighbors.set(cand, rm); }
    lm.set(left, (lm.get(left) || 0) + 1);
    rm.set(right, (rm.get(right) || 0) + 1);
  }
  static cleanText(text) {
    return String(text)
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/~~~[\s\S]*?~~~/g, " ")
      .replace(/`[^`]*`/g, " ")
      .replace(/!\[[^\]]*\]\([^)]+\)/g, " ")
      .replace(/\[[^\]]+\]\([^)]+\)/g, " ")
      .replace(/^\s*-\s+\*\*#[a-z0-9][a-z0-9-]*\*\*.*$/gm, " ")
      .replace(/^\s*#{1,6}\s+/gm, " ")
      .replace(/[*_>|]+/g, " ");
  }
  fit(text) {
    const cleaned = KeywordExtractor.cleanText(text);
    const sentences = cleaned.split(KEYWORD_SENTENCE_SPLIT_RE).filter((s) => s.length >= 2);
    for (const sent of sentences) this._scanSentence(sent);
    return this;
  }
  _scanSentence(sent) {
    const arr = Array.from(sent);
    const n = arr.length;
    for (let i = 0; i < n; i++) {
      if (isCJK(arr[i])) this._inc(arr[i]);
      this.totalChars++;
    }
    for (let i = 0; i < n; i++) {
      if (!isCJK(arr[i])) continue;
      for (let L = this.minLen; L <= this.maxLen && i + L <= n; L++) {
        let ok = true;
        for (let k = 0; k < L; k++) {
          if (!isCJK(arr[i + k])) { ok = false; break; }
        }
        if (!ok) break;
        const cand = arr.slice(i, i + L).join("");
        this._inc(cand);
        const left = i > 0 ? arr[i - 1] : "<BOS>";
        const right = i + L < n ? arr[i + L] : "<EOS>";
        this._addNeighbor(cand, left, right);
      }
    }
    const tokenRe = /[A-Za-z][A-Za-z0-9+\-]*/g;
    let m;
    while ((m = tokenRe.exec(sent)) !== null) {
      const tok = m[0];
      if (tok.length < this.minAsciiLen) continue;
      this._inc(tok);
      const startIdx = m.index;
      const endIdx = m.index + tok.length;
      const left = startIdx > 0 ? sent[startIdx - 1] : "<BOS>";
      const right = endIdx < sent.length ? sent[endIdx] : "<EOS>";
      this._addNeighbor(tok, left, right);
    }
  }
  _prob(token) { return (this.ngramFreq.get(token) || 0) / Math.max(this.totalChars, 1); }
  cohesion(word) {
    if (/^[A-Za-z][A-Za-z0-9+\-]*$/.test(word)) {
      return Math.log(this.ngramFreq.get(word) || 1) + 1;
    }
    const arr = Array.from(word);
    if (arr.length < 2) return 0;
    const pWord = this._prob(word);
    if (pWord <= 0) return 0;
    let minPmi = Infinity;
    for (let i = 1; i < arr.length; i++) {
      const pl = this._prob(arr.slice(0, i).join(""));
      const pr = this._prob(arr.slice(i).join(""));
      if (pl <= 0 || pr <= 0) return 0;
      const pmi = Math.log(pWord / (pl * pr));
      if (pmi < minPmi) minPmi = pmi;
    }
    return minPmi === Infinity ? 0 : minPmi;
  }
  discover({ topK = 80 } = {}) {
    const results = [];
    for (const [word, freq] of this.ngramFreq) {
      if (freq < this.minFreq) continue;
      const isAscii = /^[A-Za-z][A-Za-z0-9+\-]*$/.test(word);
      if (!isAscii) {
        const arr = Array.from(word);
        if (arr.length < this.minLen || arr.length > this.maxLen) continue;
      } else if (word.length < this.minAsciiLen) continue;
      const coh = this.cohesion(word);
      if (coh < this.minPmi) continue;
      const leftEnt = entropyOfMap(this.leftNeighbors.get(word) || new Map());
      const rightEnt = entropyOfMap(this.rightNeighbors.get(word) || new Map());
      if (leftEnt < this.minEntropy || rightEnt < this.minEntropy) continue;
      const score = freq * coh * Math.min(leftEnt, rightEnt);
      results.push({ word, freq, score });
    }
    results.sort((a, b) => b.score - a.score);
    const kept = [];
    for (const r of results) {
      let suppress = false;
      for (let k = 0; k < kept.length; k++) {
        const o = kept[k];
        if (o.word === r.word) continue;
        if (o.word.includes(r.word) && o.freq >= r.freq * 0.6) { suppress = true; break; }
        if (r.word.includes(o.word) && r.freq >= o.freq * 0.6 && r.word.length > o.word.length) {
          kept.splice(k, 1); k--;
        }
      }
      if (!suppress) kept.push(r);
      if (kept.length >= topK) break;
    }
    return kept;
  }
  keywordsForBlock(blockText, candidates, topN = 5) {
    const cleaned = KeywordExtractor.cleanText(blockText);
    const hits = [];
    for (const c of candidates) {
      let cnt = 0;
      let idx = 0;
      while ((idx = cleaned.indexOf(c.word, idx)) !== -1) { cnt++; idx += c.word.length; }
      if (cnt > 0) hits.push({ word: c.word, score: c.score * Math.log(cnt + 1) });
    }
    hits.sort((a, b) => b.score - a.score);
    const out = [];
    for (const h of hits) {
      let skip = false;
      for (const o of out) {
        if (o.includes(h.word) || h.word.includes(o)) { skip = true; break; }
      }
      if (!skip) out.push(h.word);
      if (out.length >= topN) break;
    }
    return out;
  }
}

// --- structural tag detector (port of detectStructuralTags) ---

function extractTableColumnHeaders(bodyText) {
  const lines = bodyText.split(/\r?\n/);
  for (let i = 0; i < lines.length - 1; i++) {
    const headerLine = lines[i];
    const sepLine = lines[i + 1] || "";
    if (TABLE_ROW_RE.test(headerLine) && TABLE_SEP_RE.test(sepLine)) {
      let body = headerLine.trim();
      if (body.startsWith("|")) body = body.slice(1);
      if (body.endsWith("|")) body = body.slice(0, -1);
      const out = [];
      for (const raw of body.split("|")) {
        const cleaned = raw
          .replace(/`[^`]*`/g, "")
          .replace(/\*\*([^*]+)\*\*/g, "$1")
          .replace(/\*([^*]+)\*/g, "$1")
          .replace(/^[\s—–-]+|[\s—–-]+$/g, "")
          .trim();
        if (cleaned.length >= 1 && cleaned.length <= 24 && /[A-Za-z一-鿿0-9]/.test(cleaned)) {
          out.push(cleaned);
        }
      }
      return out;
    }
  }
  return [];
}

export function detectStructuralTags(bodyText, blockType) {
  const tags = [];
  let mm;
  // Reset state — global regex shared across calls.
  MERMAID_BLOCK_RE.lastIndex = 0;
  while ((mm = MERMAID_BLOCK_RE.exec(bodyText)) !== null) {
    if (!tags.includes("mermaid")) tags.push("mermaid");
    for (const rawLine of mm[1].split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line) continue;
      if (line.startsWith("%%") || line.startsWith("---")) continue;
      const idM = line.match(MERMAID_DIAGRAM_ID_RE);
      if (idM) {
        const dt = idM[1];
        if (dt !== "title" && !tags.includes(dt)) tags.push(dt);
      }
      break;
    }
  }
  if (SVG_FENCE_RE.test(bodyText) && !tags.includes("svg")) tags.push("svg");
  if (blockType === "table" || blockType === "targets") {
    for (const h of extractTableColumnHeaders(bodyText)) {
      if (!tags.includes(h)) tags.push(h);
    }
  }
  return tags;
}
