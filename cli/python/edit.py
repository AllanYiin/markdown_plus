"""
Markdown+ block-granular edit API (Layer 4).

The query API (query.py) lets an agent *read* a Markdown+ document one block at
a time. This module lets it *write* the same way: change one block's body, patch
one block's metadata, insert a block, or archive a block — all without
re-emitting the whole file. That is the whole point — re-outputting an entire
document just to touch one block is exactly the token waste Markdown+ exists to
avoid.

Four operations:
    update_block_body(path, id, new_body)      — replace one block's body
    update_block_metadata(path, id, patch)     — patch inline-code metadata
    add_block(path, block, parent_id/after_id) — insert a new block
    archive_block(path, id, superseded_by)     — deprecate without deleting

Design notes:
  - Writes are atomic: a temp file in the same directory + os.replace().
  - Original newline style (\\n vs \\r\\n) and final-newline presence are
    preserved.
  - Body content is auto-indented to the block's nesting level — callers pass
    plain text, the module handles layout.
  - After any write, the query.py parse cache is cleared so the next read is
    never stale.

Built on the parser from validator.py — same directory.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import query
from validator import Block, parse_blocks

# `- ` bullet prefix is 2 chars wide; body content aligns after it.
BODY_INDENT_OFFSET = 2
_SPLIT_RE = re.compile(r"\r\n|\r|\n")


# --- internal helpers ---

def _read(path: str | Path) -> tuple[list[str], str, bool, list[Block]]:
    """Read a file preserving newline style. Returns
    (logical_lines, newline, had_final_newline, parsed_blocks).

    `logical_lines` is indexed identically to validator.parse_blocks line
    numbers (1-indexed there → line N is logical_lines[N-1])."""
    with open(path, encoding="utf-8", newline="") as f:  # newline="" → no translation
        raw = f.read()
    newline = "\r\n" if "\r\n" in raw else ("\r" if "\r" in raw else "\n")
    had_final_nl = raw.endswith(("\n", "\r"))
    lines = raw.splitlines()  # matches parse_blocks' own splitlines indexing
    blocks, _ = parse_blocks(raw)
    return lines, newline, had_final_nl, blocks


def _write_atomic(path: str | Path, lines: list[str], newline: str,
                  final_nl: bool) -> None:
    """Write lines back atomically (temp file + os.replace), then clear the
    query.py parse cache so the next read re-parses."""
    path = Path(path)
    out = newline.join(lines) + (newline if final_nl else "")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, path)  # atomic on the same filesystem
    except BaseException:
        # best-effort cleanup if the replace never happened
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    query.clear_cache()


def _by_id(blocks: list[Block]) -> dict[str, Block]:
    return {b.id: b for b in blocks}


def _require(blocks: list[Block], block_id: str, path: str | Path) -> tuple[int, Block]:
    """Return (index_in_document_order, block). Raises KeyError if not found."""
    for i, b in enumerate(blocks):
        if b.id == block_id:
            return i, b
    raise KeyError(f"block id {block_id!r} not found in {path}")


def _own_body_end(blocks: list[Block], idx: int, total_lines: int) -> int:
    """1-indexed last line of block idx's *own* body (before the next block
    header of any kind). Equals the header line if the block has no body."""
    if idx + 1 < len(blocks):
        return blocks[idx + 1].line - 1
    return total_lines


def _subtree_end(blocks: list[Block], idx: int, total_lines: int) -> int:
    """1-indexed last line of block idx's whole subtree (before the next block
    at the same or shallower indent)."""
    b = blocks[idx]
    for j in range(idx + 1, len(blocks)):
        if blocks[j].indent <= b.indent:
            return blocks[j].line - 1
    return total_lines


def _indent_body(new_body: str, indent: int) -> list[str]:
    """Split plain body text into lines and indent each non-blank line to
    `indent` spaces. Trailing blank lines are stripped (callers get a clean
    block; spacing between blocks is managed separately)."""
    pad = " " * indent
    out = [pad + ln.strip() if ln.strip() else "" for ln in _SPLIT_RE.split(new_body)]
    while out and out[-1] == "":
        out.pop()
    return out


def _emit_header(indent: int, block_id: str, metadata: dict[str, str]) -> str:
    """Render a block header line: `<indent>- **#id** `k:v` `k:v` ...`."""
    head = f"{' ' * indent}- **#{block_id}**"
    pairs = "".join(f" `{k}:{v}`" for k, v in metadata.items())
    return head + pairs


def _ordered_metadata(existing: dict[str, str], patch: dict[str, str | None]) -> dict[str, str]:
    """Apply `patch` to `existing` metadata. Value None removes a key. Existing
    key order is preserved; new keys are appended. `type` is forced first."""
    result: dict[str, str] = dict(existing)
    for k, v in patch.items():
        if v is None:
            result.pop(k, None)
        else:
            result[k] = str(v)
    if "type" in result:  # keep type: leading, it's the block's primary tag
        result = {"type": result["type"], **{k: v for k, v in result.items() if k != "type"}}
    return result


# --- public edit API ---

def update_block_body(path: str | Path, block_id: str, new_body: str) -> dict:
    """Replace one block's body. The header line is preserved verbatim; only
    the lines between this header and the next block header change.

    `new_body` is plain text (no indentation needed) — it is auto-indented to
    the block's nesting level. Returns a small summary dict."""
    lines, newline, final_nl, blocks = _read(path)
    idx, b = _require(blocks, block_id, path)
    body_start = b.line  # 0-indexed start of body == 1-indexed header line
    body_end = _own_body_end(blocks, idx, len(lines))  # 1-indexed inclusive

    new_lines = _indent_body(new_body, b.indent + BODY_INDENT_OFFSET)
    # keep one blank line before the following block, if any
    tail = lines[body_end:]
    if idx + 1 < len(blocks) and new_lines:
        new_lines = new_lines + [""]

    rebuilt = lines[:body_start] + new_lines + tail
    _write_atomic(path, rebuilt, newline, final_nl)
    return {
        "id": b.id,
        "op": "update_block_body",
        "old_body_lines": body_end - body_start,
        "new_body_lines": len(new_lines),
    }


def update_block_metadata(path: str | Path, block_id: str,
                          patch: dict[str, str | None]) -> dict:
    """Patch a block's inline-code metadata. In `patch`, a string value sets a
    key, `None` removes it. Only the header line is rewritten.

    Example: update_block_metadata(p, "auth-v1",
                                   {"status": "deprecated", "superseded-by": "auth-v2"})"""
    lines, newline, final_nl, blocks = _read(path)
    idx, b = _require(blocks, block_id, path)
    merged = _ordered_metadata(b.metadata, patch)
    lines[b.line - 1] = _emit_header(b.indent, b.id, merged)
    _write_atomic(path, lines, newline, final_nl)
    return {
        "id": b.id,
        "op": "update_block_metadata",
        "metadata": merged,
        "removed": [k for k, v in patch.items() if v is None and k in b.metadata],
    }


def add_block(path: str | Path, block: dict, *,
              parent_id: str | None = None, after_id: str | None = None) -> dict:
    """Insert a new block.

    `block` = {"id": str, "type": str, "metadata": {...}?, "body": str?}.

    Placement (pick at most one):
      after_id  — insert as a sibling right after that block's whole subtree.
      parent_id — insert as the last child of that block.
      neither   — append at end of file as a top-level block.
    """
    new_id = block.get("id")
    new_type = block.get("type")
    if not new_id or not new_type:
        raise ValueError("block must have at least 'id' and 'type'")
    lines, newline, final_nl, blocks = _read(path)
    by_id = _by_id(blocks)
    if new_id in by_id:
        raise ValueError(f"block id {new_id!r} already exists in {path}")
    if parent_id and after_id:
        raise ValueError("pass at most one of parent_id / after_id")

    if after_id is not None:
        idx, ref = _require(blocks, after_id, path)
        indent = ref.indent
        insert_at = _subtree_end(blocks, idx, len(lines))  # 1-indexed inclusive
    elif parent_id is not None:
        idx, parent = _require(blocks, parent_id, path)
        indent = parent.indent + BODY_INDENT_OFFSET
        insert_at = _subtree_end(blocks, idx, len(lines))
    else:
        indent = 0
        insert_at = len(lines)

    metadata = {"type": new_type, **{k: str(v) for k, v in block.get("metadata", {}).items()}}
    header = _emit_header(indent, new_id, metadata)
    body_lines = _indent_body(block.get("body", ""), indent + BODY_INDENT_OFFSET)

    # Splice cleanly: anchor at the last non-blank line at/before insert_at, so
    # the new block gets exactly one blank line before it, while the original
    # spacing before the *next* block is preserved untouched in the tail.
    anchor = insert_at
    while anchor > 0 and lines[anchor - 1].strip() == "":
        anchor -= 1
    snippet = (["", header] if anchor > 0 else [header]) + body_lines
    rebuilt = lines[:anchor] + snippet + lines[anchor:]
    while rebuilt and rebuilt[-1] == "":  # trim any file-end blank lines
        rebuilt.pop()
    _write_atomic(path, rebuilt, newline, final_nl)
    return {
        "id": new_id,
        "op": "add_block",
        "indent": indent,
        "after_line": anchor,
        "placement": "after" if after_id else ("child-of" if parent_id else "eof"),
    }


def archive_block(path: str | Path, block_id: str, *, superseded_by: str) -> dict:
    """Deprecate a block without deleting its content: sets
    status:deprecated + superseded-by:<id> + visibility:collapsed.

    This honours the Markdown+ principle that history is never deleted — the
    body stays, the viewer just collapses it."""
    lines, newline, final_nl, blocks = _read(path)
    by_id = _by_id(blocks)
    if superseded_by not in by_id:
        raise KeyError(f"superseded_by target {superseded_by!r} not found in {path}")
    result = update_block_metadata(path, block_id, {
        "status": "deprecated",
        "superseded-by": superseded_by,
        "visibility": "collapsed",
    })
    result["op"] = "archive_block"
    return result
