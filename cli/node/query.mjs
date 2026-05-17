// Markdown+ block-based query API (Layer 2) — Node ESM.
//
// Mirrors cli/python/query.py. Pure, stateless functions for progressive
// disclosure: list a document's block manifest, inspect one block's metadata,
// walk children, and only pull body content when explicitly asked.
//
// Built on parseBlocks from the browser/Node validator module.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseBlocks } from "../../public/lib/mdp-validator.mjs";
import { KeywordExtractor, detectStructuralTags } from "./keywords.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Default manifest fields — minimal set an agent needs to decide what to read next.
// `keywords` resolves to author-declared `keywords:` metadata if present,
// otherwise to auto-extracted keywords (same precedence as the HTML viewer).
export const MANIFEST_FIELDS = ["id", "type", "status", "title", "line", "keywords"];
const TITLE_MAX = 80;
const AUTO_KEYWORDS_PER_BLOCK = 5;
const AUTO_KEYWORDS_TOP_K = 80;

// --- internal helpers ---

// mtime+size keyed parse cache — see query.py for the full rationale. A
// single-file parse is sub-millisecond, but interactive-frequency callers
// (HTTP endpoints, MCP server) should not re-read + re-parse every call. The
// cache auto-invalidates the moment the file changes on disk.
const _parseCache = new Map();

function computeAutoKeywords(text, blocks) {
  // Per-document N-gram + PMI + entropy extraction, mirrors what the HTML
  // viewer computes in opts.autoKeywords. Best-effort; failures yield an empty
  // map so query operations never break.
  const out = new Map();
  if (!blocks.length) return out;
  try {
    const extractor = new KeywordExtractor();
    extractor.fit(text);
    const candidates = extractor.discover({ topK: AUTO_KEYWORDS_TOP_K });
    for (const b of blocks) {
      if (b.metadata.keywords) continue; // author wins
      const body = b.bodyLines.join("\n");
      const structural = detectStructuralTags(body, b.type);
      const kws = extractor.keywordsForBlock(body, candidates, AUTO_KEYWORDS_PER_BLOCK);
      const merged = [...structural, ...kws.filter((k) => !structural.includes(k))];
      if (merged.length) out.set(b.id, merged);
    }
  } catch (_) {
    return new Map();
  }
  return out;
}

function load(p) {
  const key = path.resolve(p);
  const st = fs.statSync(key); // throws ENOENT if missing — same as before
  const cached = _parseCache.get(key);
  if (cached && cached.mtimeMs === st.mtimeMs && cached.size === st.size) {
    return { text: cached.text, blocks: cached.blocks, autoKws: cached.autoKws };
  }
  const text = fs.readFileSync(key, "utf-8");
  const blocks = parseBlocks(text);
  const autoKws = computeAutoKeywords(text, blocks);
  _parseCache.set(key, { mtimeMs: st.mtimeMs, size: st.size, text, blocks, autoKws });
  return { text, blocks, autoKws };
}

// Drop all cached parse results. For tests / long-running processes.
export function clearCache() {
  _parseCache.clear();
}

function indexById(blocks) {
  const m = new Map();
  for (const b of blocks) m.set(b.id, b);
  return m;
}

function depthOf(block, byId) {
  let d = 1;
  const seen = new Set();
  let p = block.parent;
  while (p != null && !seen.has(p)) {
    seen.add(p);
    d += 1;
    p = byId.get(p)?.parent ?? null;
  }
  return d;
}

function requireBlock(byId, id, p) {
  const b = byId.get(id);
  if (!b) throw new Error(`block id '${id}' not found in ${p}`);
  return b;
}

function titleOf(block) {
  if (block.metadata.title) return block.metadata.title;
  for (const line of block.bodyLines) {
    const s = line.trim();
    if (!s) continue;
    if (/^(```|~~~|\||!\[|\*)/.test(s)) continue;
    const clean = s.replace(/[*_`#>]/g, "").trim();
    if (clean) return clean.length > TITLE_MAX ? clean.slice(0, TITLE_MAX) + "…" : clean;
  }
  return block.id.replace(/-/g, " ");
}

function summaryOf(block) {
  const parts = [];
  for (const line of block.bodyLines) {
    const s = line.trim();
    if (!s) { if (parts.length) break; else continue; }
    if (/^(```|~~~|\||!\[)/.test(s)) break;
    parts.push(s);
  }
  return parts.join(" ").replace(/[*_`]/g, "").trim();
}

function fieldOf(block, field, byId, autoKws) {
  switch (field) {
    case "id": return block.id;
    case "type": return block.type;
    case "line": return block.line;
    case "title": return titleOf(block);
    case "summary": return summaryOf(block);
    case "status": return block.metadata.status ?? null;
    case "parent": return block.parent;
    case "children": return [...block.children];
    case "depth": return depthOf(block, byId);
    case "metadata": return { ...block.metadata };
    case "auto_keywords": return [...(autoKws?.get(block.id) ?? [])];
    case "keywords": {
      const raw = block.metadata.keywords;
      if (raw) return raw.split(",").map((k) => k.trim()).filter(Boolean);
      return [...(autoKws?.get(block.id) ?? [])];
    }
    default: return block.metadata[field] ?? null;
  }
}

function matchesWhere(block, where) {
  for (const [key, want] of Object.entries(where)) {
    let have;
    if (key === "type") have = block.type;
    else if (key === "parent") have = block.parent;
    else if (key === "id") have = block.id;
    else have = block.metadata[key] ?? null;
    if (want === "*") {
      if (have == null || have === "") return false;
    } else if (have !== want) {
      return false;
    }
  }
  return true;
}

function lineRanges(blocks, totalLines) {
  // For each block id: [ownEnd, subtreeEnd], 1-indexed inclusive.
  const ranges = new Map();
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    const ownEnd = i + 1 < blocks.length ? blocks[i + 1].line - 1 : totalLines;
    let subtreeEnd = totalLines;
    for (let j = i + 1; j < blocks.length; j++) {
      if (blocks[j].indent <= b.indent) { subtreeEnd = blocks[j].line - 1; break; }
    }
    ranges.set(b.id, [ownEnd, subtreeEnd]);
  }
  return ranges;
}

// --- public query API ---

export function listBlocks(p, { depth = null, where = null, fields = null } = {}) {
  fields = fields || MANIFEST_FIELDS;
  const { blocks, autoKws } = load(p);
  const byId = indexById(blocks);
  const out = [];
  for (const b of blocks) {
    if (depth != null && depthOf(b, byId) > depth) continue;
    if (where && !matchesWhere(b, where)) continue;
    const row = {};
    for (const f of fields) row[f] = fieldOf(b, f, byId, autoKws);
    out.push(row);
  }
  return out;
}

export function getBlockMeta(p, blockId) {
  const { blocks, autoKws } = load(p);
  const byId = indexById(blocks);
  const b = requireBlock(byId, blockId, p);
  return {
    id: b.id,
    type: b.type,
    line: b.line,
    depth: depthOf(b, byId),
    parent: b.parent,
    children: [...b.children],
    title: titleOf(b),
    summary: summaryOf(b),
    metadata: { ...b.metadata },
    auto_keywords: [...(autoKws?.get(b.id) ?? [])],
    body_line_count: b.bodyLines.length,
  };
}

export function listChildren(p, blockId) {
  const { blocks } = load(p);
  return [...requireBlock(indexById(blocks), blockId, p).children];
}

export function readBlock(p, blockId, { includeChildren = false, maxLines = null } = {}) {
  const { text, blocks } = load(p);
  const lines = text.split(/\r?\n/);
  const byId = indexById(blocks);
  const b = requireBlock(byId, blockId, p);
  const [ownEnd, subtreeEnd] = lineRanges(blocks, lines.length).get(blockId);
  const end = includeChildren ? subtreeEnd : ownEnd;
  let sliceLines = lines.slice(b.line - 1, end);
  let truncated = false;
  if (maxLines != null && sliceLines.length > maxLines) {
    sliceLines = sliceLines.slice(0, maxLines);
    truncated = true;
  }
  return {
    id: b.id,
    type: b.type,
    line: b.line,
    end_line: b.line + sliceLines.length - 1,
    include_children: includeChildren,
    truncated,
    body: sliceLines.join("\n"),
  };
}

// Snippet windowing — mirrors _make_snippet in query.py. A keyword is CJK if
// it contains any CJK character; that decides whether the snippet window is
// measured in characters (CJK) or whitespace-separated words (ASCII). Mixed
// input lands in the CJK branch because the surrounding text is usually
// Chinese in that case.
const CJK_RE = /[぀-ヿ㐀-䶿一-鿿豈-﫿]/;
const WORD_RE = /\S+/g;

function keywordIsCJK(keyword) {
  return CJK_RE.test(keyword);
}

function findHits(text, keyword) {
  // Case-insensitive substring search; non-overlapping matches in source order.
  if (!text || !keyword) return [];
  const haystack = text.toLowerCase();
  const needle = keyword.toLowerCase();
  const klen = needle.length;
  const out = [];
  let pos = 0;
  while (true) {
    const idx = haystack.indexOf(needle, pos);
    if (idx < 0) return out;
    out.push([idx, idx + klen]);
    pos = idx + Math.max(1, klen);
  }
}

function wordPositions(text) {
  // Return [start, end] for every \S+ token in text. Used to find word
  // boundaries `words` tokens back / forward without re-tokenizing the source.
  const out = [];
  WORD_RE.lastIndex = 0;
  let m;
  while ((m = WORD_RE.exec(text)) !== null) out.push([m.index, m.index + m[0].length]);
  return out;
}

function makeSnippet(text, start, end, keyword, { chars = 5, words = 5 } = {}) {
  // CJK keyword → `chars` chars each side; ASCII keyword → `words` words each
  // side. Both branches slice the raw source so original punctuation/markup
  // survives, then collapse internal whitespace so snippets stay single-line.
  // `…` marks truncation on the truncated side.
  let s, e;
  if (keywordIsCJK(keyword)) {
    s = Math.max(0, start - chars);
    e = Math.min(text.length, end + chars);
  } else {
    const prefixWords = wordPositions(text.slice(0, start));
    const suffixWords = wordPositions(text.slice(end));
    s = prefixWords.length > words ? prefixWords[prefixWords.length - words][0] : 0;
    e = suffixWords.length > words ? end + suffixWords[words - 1][1] : text.length;
  }
  const leftDots = s > 0 ? "…" : "";
  const rightDots = e < text.length ? "…" : "";
  const body = text.slice(s, e).replace(/\s+/g, " ").trim();
  return leftDots + body + rightDots;
}

function fieldTextForSearch(block, field, byId, autoKws) {
  // Flatten one field as a string for substring search. Returns null when the
  // field is empty so the caller can skip it. `body` is special-cased because
  // it doesn't go through fieldOf (which never returns body).
  if (field === "body") return block.bodyLines.length ? block.bodyLines.join("\n") : null;
  const v = fieldOf(block, field, byId, autoKws);
  if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) return null;
  if (Array.isArray(v)) return v.map(String).join(", ");
  return String(v);
}

// Two call modes:
//   single keyword: searchBlocks(path, "部署")
//   multi-keyword OR: searchBlocks(path, null, { anyOf: ["部署", "風險"] })
// Each row is MANIFEST_FIELDS + matched:[which queries actually hit] +
// snippets:[{field, keyword, snippet}] — truncated context windows around each
// hit (`contextChars` chars for CJK keywords, `contextWords` words for ASCII).
// Body is always scanned: snippets are bounded windows, not full body, so
// scanning body costs nothing on the response side. Use `limit` to cap result count.
export function searchBlocks(
  p,
  queryStr = null,
  {
    anyOf = null,
    fields = null,
    limit = 20,
    snippets = true,
    maxSnippets = 5,
    contextChars = 5,
    contextWords = 5,
  } = {},
) {
  const queries = [];
  if (queryStr) queries.push(queryStr);
  if (anyOf) {
    for (const q of anyOf) if (q && !queries.includes(q)) queries.push(q);
  }
  if (!queries.length) return [];
  fields = fields || ["title", "summary", "id", "type", "tags", "status", "keywords"];
  if (!fields.includes("body")) fields = [...fields, "body"];
  const { blocks, autoKws } = load(p);
  const byId = indexById(blocks);
  const scored = [];
  for (const b of blocks) {
    const fieldTexts = [];
    for (const f of fields) {
      const txt = fieldTextForSearch(b, f, byId, autoKws);
      if (txt != null) fieldTexts.push([f, txt]);
    }
    let total = 0;
    const matched = [];
    const blockSnippets = [];
    for (const keyword of queries) {
      let keywordHit = false;
      for (const [fieldName, fieldText] of fieldTexts) {
        const hits = findHits(fieldText, keyword);
        if (!hits.length) continue;
        keywordHit = true;
        total += hits.length;
        if (snippets) {
          for (const [start, end] of hits) {
            if (blockSnippets.length >= maxSnippets) break;
            blockSnippets.push({
              field: fieldName,
              keyword,
              snippet: makeSnippet(fieldText, start, end, keyword, {
                chars: contextChars,
                words: contextWords,
              }),
            });
          }
        }
        if (snippets && blockSnippets.length >= maxSnippets) break;
      }
      if (keywordHit && !matched.includes(keyword)) matched.push(keyword);
    }
    if (total) scored.push([total, b, matched, blockSnippets]);
  }
  scored.sort((a, b) => b[0] - a[0] || a[1].line - b[1].line);
  return scored.slice(0, limit).map(([, b, matched, snip]) => {
    const row = {};
    for (const f of MANIFEST_FIELDS) row[f] = fieldOf(b, f, byId, autoKws);
    row.matched = matched;
    if (snippets) row.snippets = snip;
    return row;
  });
}

export function resolveXref(p, blockId) {
  const { blocks } = load(p);
  const byId = indexById(blocks);
  const b = requireBlock(byId, blockId, p);

  const ref = (targetId) => {
    if (!targetId) return null;
    const t = byId.get(targetId);
    if (!t) return { id: targetId, found: false };
    return {
      id: t.id,
      found: true,
      type: t.type,
      status: t.metadata.status ?? null,
      line: t.line,
      title: titleOf(t),
    };
  };

  const relatedIds = (b.metadata.related || "").match(/[a-z0-9][a-z0-9-]*/g) || [];
  return {
    id: b.id,
    parent: ref(b.parent),
    children: b.children.map(ref),
    superseded_by: ref(b.metadata["superseded-by"]),
    supersedes: blocks
      .filter((x) => x.metadata["superseded-by"] === b.id)
      .map((x) => ref(x.id)),
    related: relatedIds.map(ref),
  };
}

export function tree(p) {
  const { blocks } = load(p);
  const byId = indexById(blocks);
  const node = (b) => ({
    id: b.id,
    type: b.type,
    status: b.metadata.status ?? null,
    title: titleOf(b),
    line: b.line,
    children: b.children.map((c) => node(byId.get(c))),
  });
  return blocks.filter((b) => b.parent == null).map(node);
}
