"""
Markdown+ block-based query API (Layer 2).

Pure, stateless functions for *progressive disclosure*: an AI agent can list a
document's block manifest, inspect one block's metadata, walk children, and
only pull body content when it explicitly asks — instead of reading the whole
file line-by-line.

Access pattern this enables:

    1. list_blocks(path, depth=1)    → manifest: [{id, type, status, title, line}]
    2. get_block_meta(path, id)      → one block's full metadata (no body)
    3. list_children(path, id)       → direct child ids
    4. read_block(path, id)          → body markdown (the only call that costs tokens)

Most queries only need steps 1-2. Reading the whole file is the worst case,
not the default.

Every function re-parses the file on each call. Single-file parse is
sub-millisecond, so no index/cache layer is needed for single-document use
(cross-repo indexing is Layer 3, out of scope here).

Built on the parser from validator.py — same directory.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from validator import Block, parse_blocks

# Default manifest fields — the minimal set an agent needs to decide what to read next.
MANIFEST_FIELDS = ["id", "type", "status", "title", "line"]
TITLE_MAX = 80


# --- internal helpers ---

# mtime+size keyed parse cache. A single-file parse is sub-millisecond, but the
# /api/mdp/* HTTP endpoints (and MCP server) can be hit at interactive
# frequency — re-reading and re-parsing on every call is pure waste. The cache
# auto-invalidates the moment the file changes on disk (mtime or size differ),
# so callers never see stale data; no manual invalidation needed in normal use.
_PARSE_CACHE: dict[str, tuple[float, int, str, list[Block]]] = {}


def _load(path: str | Path) -> tuple[str, list[Block]]:
    """Read + parse a Markdown+ file, with an mtime/size-based cache.
    Returns (raw_text, blocks). Cache auto-invalidates when the file changes."""
    key = str(Path(path).resolve())
    st = os.stat(key)  # raises FileNotFoundError if missing — same as before
    cached = _PARSE_CACHE.get(key)
    if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2], cached[3]
    text = Path(key).read_text(encoding="utf-8")
    blocks, _ = parse_blocks(text)
    _PARSE_CACHE[key] = (st.st_mtime, st.st_size, text, blocks)
    return text, blocks


def clear_cache() -> None:
    """Drop all cached parse results. For tests / long-running processes that
    want to force a clean re-read."""
    _PARSE_CACHE.clear()


def _index(blocks: list[Block]) -> dict[str, Block]:
    return {b.id: b for b in blocks}


def _depth(block: Block, by_id: dict[str, Block]) -> int:
    """1 = top-level, 2 = direct child, ... Walks the parent chain."""
    d = 1
    seen: set[str] = set()
    p = block.parent
    while p is not None and p not in seen:
        seen.add(p)
        d += 1
        parent = by_id.get(p)
        p = parent.parent if parent else None
    return d


def _require(by_id: dict[str, Block], block_id: str, path: str | Path) -> Block:
    b = by_id.get(block_id)
    if b is None:
        raise KeyError(f"block id {block_id!r} not found in {path}")
    return b


def _title(block: Block) -> str:
    """Best-effort human title: explicit `title:` metadata > first prose line > humanized id."""
    explicit = block.metadata.get("title")
    if explicit:
        return explicit
    for line in block.body_lines:
        s = line.strip()
        if not s:
            continue
        # skip code fences, tables, images, captions
        if s.startswith(("```", "~~~", "|", "![", "*")):
            continue
        s = re.sub(r"[*_`#>]", "", s).strip()
        if s:
            return s[:TITLE_MAX] + ("…" if len(s) > TITLE_MAX else "")
    return block.id.replace("-", " ")


def _summary(block: Block) -> str:
    """First prose paragraph of the block body, markdown noise stripped."""
    parts: list[str] = []
    for line in block.body_lines:
        s = line.strip()
        if not s:
            if parts:
                break
            continue
        if s.startswith(("```", "~~~", "|", "![")):
            break
        parts.append(s)
    return re.sub(r"[*_`]", "", " ".join(parts)).strip()


def _field(block: Block, field: str, by_id: dict[str, Block]):
    """Resolve a single named field for a block (used by manifest projection)."""
    if field == "id":
        return block.id
    if field == "type":
        return block.type
    if field == "line":
        return block.line
    if field == "title":
        return _title(block)
    if field == "summary":
        return _summary(block)
    if field == "status":
        return block.metadata.get("status")
    if field == "parent":
        return block.parent
    if field == "children":
        return list(block.children)
    if field == "depth":
        return _depth(block, by_id)
    if field == "metadata":
        return dict(block.metadata)
    # any other field name → metadata lookup (tags, owner, priority, ...)
    return block.metadata.get(field)


def _matches(block: Block, where: dict[str, str]) -> bool:
    """Filter predicate. `type`/`parent`/`id` match block attributes; everything
    else matches metadata. Value `*` matches any present value."""
    for key, want in where.items():
        if key == "type":
            have = block.type
        elif key == "parent":
            have = block.parent
        elif key == "id":
            have = block.id
        else:
            have = block.metadata.get(key)
        if want == "*":
            if have in (None, ""):
                return False
        elif have != want:
            return False
    return True


def _line_ranges(blocks: list[Block], total_lines: int) -> dict[str, tuple[int, int]]:
    """For each block id, compute (own_end, subtree_end), 1-indexed inclusive.

    own_end     — last line before the next block header of any kind.
    subtree_end — last line before the next block at the same or shallower indent.
    """
    ranges: dict[str, tuple[int, int]] = {}
    for i, b in enumerate(blocks):
        own_end = blocks[i + 1].line - 1 if i + 1 < len(blocks) else total_lines
        subtree_end = total_lines
        for j in range(i + 1, len(blocks)):
            if blocks[j].indent <= b.indent:
                subtree_end = blocks[j].line - 1
                break
        ranges[b.id] = (own_end, subtree_end)
    return ranges


# --- public query API ---

def list_blocks(
    path: str | Path,
    *,
    depth: int | None = None,
    where: dict[str, str] | None = None,
    fields: list[str] | None = None,
) -> list[dict]:
    """Return a block manifest — metadata only, no body content.

    depth   — 1 = top-level only, 2 = include direct children, etc. None = all.
    where   — filter, e.g. {"type": "decision", "status": "open"}.
    fields  — which fields to project. Defaults to MANIFEST_FIELDS.
    """
    fields = fields or MANIFEST_FIELDS
    _, blocks = _load(path)
    by_id = _index(blocks)
    out: list[dict] = []
    for b in blocks:
        if depth is not None and _depth(b, by_id) > depth:
            continue
        if where and not _matches(b, where):
            continue
        out.append({f: _field(b, f, by_id) for f in fields})
    return out


def get_block_meta(path: str | Path, block_id: str) -> dict:
    """Return one block's full metadata — still no body content."""
    _, blocks = _load(path)
    by_id = _index(blocks)
    b = _require(by_id, block_id, path)
    return {
        "id": b.id,
        "type": b.type,
        "line": b.line,
        "depth": _depth(b, by_id),
        "parent": b.parent,
        "children": list(b.children),
        "title": _title(b),
        "summary": _summary(b),
        "metadata": dict(b.metadata),
        "body_line_count": len(b.body_lines),
    }


def list_children(path: str | Path, block_id: str) -> list[str]:
    """Return the direct child block ids of a block."""
    _, blocks = _load(path)
    by_id = _index(blocks)
    return list(_require(by_id, block_id, path).children)


def read_block(
    path: str | Path,
    block_id: str,
    *,
    include_children: bool = False,
    max_lines: int | None = None,
) -> dict:
    """Return a block's body markdown — the only call that pulls real content.

    include_children — if True, include the whole subtree (child headers + bodies).
    max_lines        — cap the returned line count; sets `truncated: True` if hit.

    The returned `body` includes this block's own header line, so it is a valid
    standalone Markdown+ snippet.
    """
    text, blocks = _load(path)
    lines = text.splitlines()
    by_id = _index(blocks)
    b = _require(by_id, block_id, path)
    own_end, subtree_end = _line_ranges(blocks, len(lines))[block_id]
    end = subtree_end if include_children else own_end
    slice_lines = lines[b.line - 1:end]
    truncated = False
    if max_lines is not None and len(slice_lines) > max_lines:
        slice_lines = slice_lines[:max_lines]
        truncated = True
    return {
        "id": b.id,
        "type": b.type,
        "line": b.line,
        "end_line": b.line + len(slice_lines) - 1,
        "include_children": include_children,
        "truncated": truncated,
        "body": "\n".join(slice_lines),
    }


def search_blocks(
    path: str | Path,
    query: str,
    *,
    fields: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Lightweight keyword search over metadata + title/summary — never scans body.

    Case-insensitive substring match. Results ranked by match count, then line.
    Returns manifest-shaped dicts (MANIFEST_FIELDS).
    """
    fields = fields or ["title", "summary", "id", "type", "tags", "status"]
    _, blocks = _load(path)
    by_id = _index(blocks)
    q = query.lower()
    scored: list[tuple[int, Block]] = []
    for b in blocks:
        haystack = " ".join(
            str(_field(b, f, by_id)).lower()
            for f in fields
            if _field(b, f, by_id) not in (None, "")
        )
        count = haystack.count(q)
        if count:
            scored.append((count, b))
    scored.sort(key=lambda t: (-t[0], t[1].line))
    return [
        {f: _field(b, f, by_id) for f in MANIFEST_FIELDS}
        for _, b in scored[:limit]
    ]


def resolve_xref(path: str | Path, block_id: str) -> dict:
    """Follow a block's relationships: parent, children, superseded-by /
    supersedes, and `related:` ids. Each reference is resolved to a small
    descriptor (or marked found:false if it points nowhere)."""
    _, blocks = _load(path)
    by_id = _index(blocks)
    b = _require(by_id, block_id, path)

    def ref(target_id: str | None) -> dict | None:
        if not target_id:
            return None
        t = by_id.get(target_id)
        if t is None:
            return {"id": target_id, "found": False}
        return {
            "id": t.id,
            "found": True,
            "type": t.type,
            "status": t.metadata.get("status"),
            "line": t.line,
            "title": _title(t),
        }

    related_ids = re.findall(r"[a-z0-9][a-z0-9-]*", b.metadata.get("related", ""))
    return {
        "id": b.id,
        "parent": ref(b.parent),
        "children": [ref(c) for c in b.children],
        "superseded_by": ref(b.metadata.get("superseded-by")),
        "supersedes": [
            ref(x.id) for x in blocks if x.metadata.get("superseded-by") == b.id
        ],
        "related": [ref(r) for r in related_ids],
    }


def tree(path: str | Path) -> list[dict]:
    """Return the full block hierarchy as nested dicts (roots → children).
    Metadata-only — no body content."""
    _, blocks = _load(path)
    by_id = _index(blocks)

    def node(b: Block) -> dict:
        return {
            "id": b.id,
            "type": b.type,
            "status": b.metadata.get("status"),
            "title": _title(b),
            "line": b.line,
            "children": [node(by_id[c]) for c in b.children],
        }

    return [node(b) for b in blocks if b.parent is None]
