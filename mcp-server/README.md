# Markdown+ MCP server

Exposes the Layer 2 block-query API (see [`../docs/08-block-based-query.md`](../docs/08-block-based-query.md))
as **MCP tools**, so Claude — or any MCP-aware client — can do *progressive
disclosure* over a Markdown+ document instead of reading the whole file into
context.

It reuses [`../cli/python/query.py`](../cli/python/query.py) verbatim — the same
logic behind the `mdp` CLI and the `/api/mdp/*` HTTP endpoints. One
implementation, three front doors.

## Install

```bash
pip install -r mcp-server/requirements.txt
```

## Run as an MCP server (stdio)

```bash
python mcp-server/mdp_mcp_server.py
```

This speaks the MCP protocol over stdio — it is what an MCP client launches,
not something you interact with directly. To wire it into **Claude Desktop**,
add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "markdown-plus": {
      "command": "python",
      "args": ["/abs/path/to/markdown_plus_repo/mcp-server/mdp_mcp_server.py"]
    }
  }
}
```

## CLI mode (no MCP client needed)

The same 7 tools are reachable straight from the command line — handy for
testing, scripting, and seeing exactly what a tool returns:

```bash
# list the 7 tools + their descriptions
python mcp-server/mdp_mcp_server.py --list-tools

# invoke one tool — args are a JSON object, matching the tool's parameters
python mcp-server/mdp_mcp_server.py --call mdp_list_blocks \
  '{"path": "public/samples/decision-record.mdp.md", "depth": 1}'

python mcp-server/mdp_mcp_server.py --call mdp_read_block \
  '{"path": "public/samples/decision-record.mdp.md", "id": "decision"}'

# standalone smoke test (defaults to a repo sample)
python mcp-server/mdp_mcp_server.py --selftest
```

Exit codes: `0` ok · `1` runtime error (file/block not found) · `2` bad usage.

## Tools

| Tool | Returns body? | Purpose |
|---|---|---|
| `mdp_list_blocks` | ✗ | Block manifest — call first |
| `mdp_get_block_meta` | ✗ | One block's full metadata |
| `mdp_list_children` | ✗ | Direct child ids |
| `mdp_read_block` | ✓ | Block body markdown — the only token-spending call |
| `mdp_search_blocks` | ✗ | Keyword search over metadata/title/summary |
| `mdp_resolve_xref` | ✗ | Follow parent/children/superseded-by/related |
| `mdp_tree` | ✗ | Full nested block hierarchy |

Unlike the `/api/mdp/*` HTTP endpoints (which sandbox `path` to `public/`), the
MCP server is a **local tool** and accepts any readable file path — same as the
`mdp` CLI.
