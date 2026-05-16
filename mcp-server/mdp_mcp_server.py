"""
Markdown+ MCP server — exposes the Layer 2 block-query API as MCP tools.

This is the most direct way to give Claude (Claude Desktop, or any MCP-aware
client) progressive-disclosure access to Markdown+ documents: instead of
dumping a whole file into context, the model calls `mdp_list_blocks` first to
see the manifest, then drills into specific blocks with `mdp_read_block`.

It reuses `cli/python/query.py` verbatim — same logic the `mdp` CLI and the
`/api/mdp/*` HTTP endpoints use. One implementation, three front doors.

------------------------------------------------------------------------------
Run as an MCP server (stdio transport — this is what an MCP client launches):

    python mcp-server/mdp_mcp_server.py

Claude Desktop config (claude_desktop_config.json):

    {
      "mcpServers": {
        "markdown-plus": {
          "command": "python",
          "args": ["/abs/path/to/markdown_plus_repo/mcp-server/mdp_mcp_server.py"]
        }
      }
    }

------------------------------------------------------------------------------
CLI mode — exercise the same tools from the command line, no MCP client needed
(useful for testing, scripting, and seeing exactly what a tool returns):

    python mcp-server/mdp_mcp_server.py --list-tools
    python mcp-server/mdp_mcp_server.py --call mdp_list_blocks '{"path": "public/samples/decision-record.mdp.md", "depth": 1}'
    python mcp-server/mdp_mcp_server.py --call mdp_read_block  '{"path": "public/samples/decision-record.mdp.md", "id": "decision"}'
    python mcp-server/mdp_mcp_server.py --selftest

Requirements:  pip install -r mcp-server/requirements.txt
"""
# NOTE: deliberately NO `from __future__ import annotations` here — FastMCP
# introspects real annotation objects to build tool schemas; stringized
# annotations break it. All hints below are Python 3.10+ native syntax.

import json
import sys
from pathlib import Path

# query.py lives in cli/python/ — reuse it instead of reimplementing.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli" / "python"))
import query  # type: ignore  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("markdown-plus")


# --- tools (reuse query.py; docstrings double as the MCP tool descriptions) ---

@mcp.tool()
def mdp_list_blocks(
    path: str,
    depth: int | None = None,
    where: dict[str, str] | None = None,
) -> list[dict]:
    """List blocks in a Markdown+ document. Returns a metadata-only manifest
    [{id, type, status, title, line}], NOT body content. ALWAYS call this first
    to discover what is in a file before reading any block — it is the cheap,
    token-light entry point for progressive disclosure.

    depth: 1 = top-level blocks only, 2 = include direct children, etc.
    where: filter by attribute/metadata, e.g. {"type": "decision", "status": "open"};
           use "*" as a value to match any present value of a key.
    """
    return query.list_blocks(path, depth=depth, where=where or None)


@mcp.tool()
def mdp_get_block_meta(path: str, id: str) -> dict:
    """Get one block's full metadata (id, type, line, depth, parent, children,
    title, summary, all key:value metadata, body line count). Still NO body
    content. Call after mdp_list_blocks to inspect a specific candidate before
    deciding to read it."""
    return query.get_block_meta(path, id)


@mcp.tool()
def mdp_list_children(path: str, id: str) -> list[str]:
    """List the direct child block ids of a block. Use to walk a document's
    hierarchy one level at a time without pulling content."""
    return query.list_children(path, id)


@mcp.tool()
def mdp_read_block(
    path: str,
    id: str,
    include_children: bool = False,
    max_lines: int | None = None,
) -> dict:
    """Read a block's body markdown. This is the ONLY tool that returns real
    content and spends tokens — call it last, only on the specific block(s) you
    actually need. The returned body includes the block's own header line, so
    it is a valid standalone Markdown+ snippet.

    include_children: if true, return the whole subtree (child headers + bodies).
    max_lines: cap returned lines; if hit, the response sets truncated:true.
    """
    return query.read_block(
        path, id, include_children=include_children, max_lines=max_lines
    )


@mcp.tool()
def mdp_search_blocks(path: str, query_text: str, limit: int = 20) -> list[dict]:
    """Lightweight keyword search across block metadata, title and summary —
    never scans body content. Case-insensitive substring match, ranked by match
    count. Returns manifest-shaped results [{id, type, status, title, line}].
    Use to locate candidate blocks by topic before reading them."""
    return query.search_blocks(path, query_text, limit=limit)


@mcp.tool()
def mdp_resolve_xref(path: str, id: str) -> dict:
    """Resolve a block's relationships: parent, children, superseded-by /
    supersedes, and related ids. Each reference is resolved to a small
    descriptor (or marked found:false if it points nowhere). Use to follow
    decision history and cross-links."""
    return query.resolve_xref(path, id)


@mcp.tool()
def mdp_tree(path: str) -> list[dict]:
    """Return the full block hierarchy of a document as nested nodes
    ({id, type, status, title, line, children}). Metadata-only, no body content.
    Use for a one-shot structural overview of a whole document."""
    return query.tree(path)


# Registry for CLI dispatch — name → callable.
TOOLS: dict = {
    "mdp_list_blocks": mdp_list_blocks,
    "mdp_get_block_meta": mdp_get_block_meta,
    "mdp_list_children": mdp_list_children,
    "mdp_read_block": mdp_read_block,
    "mdp_search_blocks": mdp_search_blocks,
    "mdp_resolve_xref": mdp_resolve_xref,
    "mdp_tree": mdp_tree,
}


# --- CLI mode (no MCP client needed) ---

def _cli_list_tools() -> int:
    print("Markdown+ MCP server — 7 tools:\n")
    for name, fn in TOOLS.items():
        first_line = (fn.__doc__ or "").strip().splitlines()[0]
        print(f"  {name}\n    {first_line}\n")
    return 0


def _cli_call(tool: str, args_json: str) -> int:
    fn = TOOLS.get(tool)
    if fn is None:
        print(f"unknown tool {tool!r}. Try --list-tools.", file=sys.stderr)
        return 2
    try:
        kwargs = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(f"invalid JSON args: {e}", file=sys.stderr)
        return 2
    if not isinstance(kwargs, dict):
        print("args must be a JSON object", file=sys.stderr)
        return 2
    try:
        result = fn(**kwargs)
    except TypeError as e:
        print(f"bad arguments for {tool}: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"file not found: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cli_selftest(path: str | None) -> int:
    sample = path or str(REPO_ROOT / "public" / "samples" / "decision-record.mdp.md")
    print(f"selftest against: {sample}\n")
    checks: list[tuple[str, bool]] = []
    try:
        manifest = mdp_list_blocks(sample, depth=1)
        checks.append(("mdp_list_blocks returns >=1 block", len(manifest) >= 1))
        first_id = manifest[0]["id"]

        meta = mdp_get_block_meta(sample, first_id)
        checks.append(("mdp_get_block_meta has no body field", "body" not in meta))

        body = mdp_read_block(sample, first_id)
        checks.append(("mdp_read_block returns body text", bool(body.get("body"))))

        tree = mdp_tree(sample)
        checks.append(("mdp_tree returns roots", len(tree) >= 1))

        children = mdp_list_children(sample, first_id)
        checks.append(("mdp_list_children returns a list", isinstance(children, list)))

        hits = mdp_search_blocks(sample, first_id.split("-")[0], limit=5)
        checks.append(("mdp_search_blocks returns a list", isinstance(hits, list)))

        xref = mdp_resolve_xref(sample, first_id)
        checks.append(("mdp_resolve_xref has 'related' key", "related" in xref))
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL — exception: {type(e).__name__}: {e}")
        return 1

    ok = True
    for label, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
        ok = ok and passed
    print(f"\n{'all checks passed' if ok else 'SELFTEST FAILED'}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        # Default: run as an MCP server over stdio (what an MCP client launches).
        mcp.run()
        return 0
    cmd = args[0]
    if cmd in ("-h", "--help"):
        print(__doc__)
        return 0
    if cmd == "--list-tools":
        return _cli_list_tools()
    if cmd == "--call":
        if len(args) < 2:
            print("usage: --call <tool> '<json-args>'", file=sys.stderr)
            return 2
        return _cli_call(args[1], args[2] if len(args) > 2 else "")
    if cmd == "--selftest":
        return _cli_selftest(args[1] if len(args) > 1 else None)
    print(f"unknown option {cmd!r}. Try --help.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
