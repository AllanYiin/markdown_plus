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

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Default manifest fields — minimal set an agent needs to decide what to read next.
export const MANIFEST_FIELDS = ["id", "type", "status", "title", "line"];
const TITLE_MAX = 80;

// --- internal helpers ---

// mtime+size keyed parse cache — see query.py for the full rationale. A
// single-file parse is sub-millisecond, but interactive-frequency callers
// (HTTP endpoints, MCP server) should not re-read + re-parse every call. The
// cache auto-invalidates the moment the file changes on disk.
const _parseCache = new Map();

function load(p) {
  const key = path.resolve(p);
  const st = fs.statSync(key); // throws ENOENT if missing — same as before
  const cached = _parseCache.get(key);
  if (cached && cached.mtimeMs === st.mtimeMs && cached.size === st.size) {
    return { text: cached.text, blocks: cached.blocks };
  }
  const text = fs.readFileSync(key, "utf-8");
  const blocks = parseBlocks(text);
  _parseCache.set(key, { mtimeMs: st.mtimeMs, size: st.size, text, blocks });
  return { text, blocks };
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

function fieldOf(block, field, byId) {
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
  const { blocks } = load(p);
  const byId = indexById(blocks);
  const out = [];
  for (const b of blocks) {
    if (depth != null && depthOf(b, byId) > depth) continue;
    if (where && !matchesWhere(b, where)) continue;
    const row = {};
    for (const f of fields) row[f] = fieldOf(b, f, byId);
    out.push(row);
  }
  return out;
}

export function getBlockMeta(p, blockId) {
  const { blocks } = load(p);
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

export function searchBlocks(p, queryStr, { fields = null, limit = 20 } = {}) {
  fields = fields || ["title", "summary", "id", "type", "tags", "status"];
  const { blocks } = load(p);
  const byId = indexById(blocks);
  const q = queryStr.toLowerCase();
  const scored = [];
  for (const b of blocks) {
    const haystack = fields
      .map((f) => fieldOf(b, f, byId))
      .filter((v) => v != null && v !== "")
      .map((v) => String(v).toLowerCase())
      .join(" ");
    let count = 0, idx = 0;
    while ((idx = haystack.indexOf(q, idx)) !== -1) { count++; idx += q.length; }
    if (count) scored.push([count, b]);
  }
  scored.sort((a, b) => b[0] - a[0] || a[1].line - b[1].line);
  return scored.slice(0, limit).map(([, b]) => {
    const row = {};
    for (const f of MANIFEST_FIELDS) row[f] = fieldOf(b, f, byId);
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
