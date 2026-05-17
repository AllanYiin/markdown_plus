# 08 — Block-based query（漸進式揭露）

Markdown+ 的格式設計本身只是地基。要真正兌現「省 token」的承諾，需要一層
**查詢 API**，讓 AI agent 不必把整份文件 dump 進 context，而是先看目錄、再看
metadata、最後只讀它真正需要的 block。

## 為什麼需要這層

純 `.md` 檔對機器只能逐列讀取——先讀前 100 列，沒找到再 100 列。很沒效率，
也浪費 token。Markdown+ 引入 **block** 概念後，內容可以分區存放，AI 的存取
模式應該是：

```
1. list_blocks(path, depth=1)   ← 只拿 manifest:[id, type, status, title, line]
2. get_block_meta(path, id)     ← 拿單一 block 的所有 metadata（仍不含 body）
3. list_children(path, id)      ← 取子 block
4. read_block(path, id)         ← 真正讀內容（唯一花 token 的一步）
```

整份檔讀完只在最壞情況發生。多數 query 只需要 step 1 + 2，根本不碰 body。

### 一個對比場景

對一份 100-block 的長 spec 文件回答「目前有哪些未決的 open decision？」：

| 做法 | tokens（量級） |
|---|---|
| 把整份檔丟給 LLM | ~20,000 |
| `list_blocks(where={type:decision,status:open})` → 8 個 manifest → `read_block` 命中那一個 | ~800 |

省下約 25 倍。這就是「漸進式揭露」真正兌現的時刻。

## Layer 2 查詢 API

實作在 [`cli/python/query.py`](../cli/python/query.py) 與
[`cli/node/query.mjs`](../cli/node/query.mjs)，兩邊邏輯對齊。所有函式都是
**純解析、單檔、無 state**——適合 stateless 呼叫。單檔重新 parse 成本 < 1ms，
所以單檔場景不需要索引層（跨 repo 多檔索引是 Layer 3，尚未實作）。

| 函式 | 回傳 | 含 body？ |
|---|---|---|
| `list_blocks(path, depth, where, fields)` | block manifest | ✗ |
| `get_block_meta(path, id)` | 單一 block 的完整 metadata | ✗ |
| `list_children(path, id)` | 直系子 block id 清單 | ✗ |
| `read_block(path, id, include_children, max_lines)` | block body markdown | ✓ |
| `search_blocks(path, query, fields, limit)` | 關鍵字搜尋，回傳命中 block + 截斷 snippet | snippet only |
| `resolve_xref(path, id)` | parent / children / superseded-by / related 關係 | ✗ |
| `tree(path)` | 巢狀 block 階層 | ✗ |

**關鍵設計：預設不回傳 body。** 每一步 AI 都要明確選擇「我要拿什麼」，
`read_block` 是唯一會花 token 的呼叫。
`search_blocks` 雖然會掃 body，但只回傳關鍵字命中處前後 5 個字元（CJK keyword）
或 5 個單字（ASCII keyword）的截斷 snippet（`…` 標示被截斷），
每個 block 上限 5 條 snippet，整體回應量還是受 `limit` 控制，不會塞整段 body。

### Python

```python
import sys; sys.path.insert(0, "cli/python")
import query as q

q.list_blocks("public/samples/decision-record.mdp.md",
              where={"type": "task", "status": "open"})
# → [{'id': 'action-rollout', 'type': 'task', 'status': 'open', 'title': '...', 'line': 33}]

q.read_block("public/samples/decision-record.mdp.md", "action-rollout")
# → {'id': 'action-rollout', 'body': '...', 'truncated': False, ...}
```

### Node

```js
import * as q from "./cli/node/query.mjs";

q.listBlocks("public/samples/decision-record.mdp.md",
             { where: { type: "task", status: "open" } });
q.readBlock("public/samples/decision-record.mdp.md", "action-rollout");
```

## CLI：`mdp`

人類與 shell script 也能直接用。Python 版 [`cli/python/mdp.py`](../cli/python/mdp.py)、
Node 版 [`cli/node/mdp.mjs`](../cli/node/mdp.mjs)，subcommand 一致。

```bash
# 列出 top-level block manifest
python cli/python/mdp.py list public/samples/decision-record.mdp.md --depth 1

# 過濾：只看 open 的 task
python cli/python/mdp.py list public/samples/decision-record.mdp.md --type task --status open

# 任意 metadata 過濾
python cli/python/mdp.py list doc.mdp.md --where owner=alice --where priority=high

# 整份階層樹
python cli/python/mdp.py tree public/samples/decision-record.mdp.md

# 單一 block 的 metadata（不含 body）
python cli/python/mdp.py get public/samples/decision-record.mdp.md decision

# 直系子 block
python cli/python/mdp.py children public/samples/decision-record.mdp.md options

# 讀 body（唯一花 token 的一步）；--children 連子樹一起讀
python cli/python/mdp.py read public/samples/decision-record.mdp.md options --children
python cli/python/mdp.py read doc.mdp.md big-block --max-lines 50

# 關鍵字搜尋（掃 metadata + title/summary + keywords + body）
# 結果每筆會帶 snippets：命中關鍵字前後 5 字元（CJK）或 5 單字（ASCII）的截斷視窗
python cli/python/mdp.py search public/samples/decision-record.mdp.md turborepo

# 跟隨關係
python cli/python/mdp.py xref public/samples/decision-record.mdp.md rejected-lerna-7
```

加 `--json` 取得機器可讀輸出。Exit code：`0` ok、`1` 錯誤（如 block id 不存在）、
`2` 用法錯誤。

Node 版用法相同：`node cli/node/mdp.mjs list <doc> ...`。

## HTTP REST：`/api/mdp/*`

[`server.py`](../server.py) 把同一套 `query.py` 邏輯暴露成 HTTP endpoint，
任何 HTTP-capable agent（LangChain tool、自家 script、curl）都能用。

| Endpoint | 參數 |
|---|---|
| `GET /api/mdp/list` | `path`, `depth`, `type`, `status`, `where`(可重複 `k=v`), `fields`(逗號分隔) |
| `GET /api/mdp/tree` | `path` |
| `GET /api/mdp/get` | `path`, `id` |
| `GET /api/mdp/children` | `path`, `id` |
| `GET /api/mdp/read` | `path`, `id`, `children`(`1`/`true`), `max_lines` |
| `GET /api/mdp/search` | `path`, `q`, `limit` |
| `GET /api/mdp/xref` | `path`, `id` |

```bash
curl "http://localhost:8000/api/mdp/list?path=samples/decision-record.mdp.md&type=task&status=open"
curl "http://localhost:8000/api/mdp/read?path=samples/decision-record.mdp.md&id=decision"
```

回應格式：`{"ok": true, "op": "...", "result": ...}`；錯誤回 `{"error": "..."}`。

**安全限制**：`path` 一律相對於 `public/` 解析，不允許跳脫該目錄（traversal
會回 `403`）。`/api/health` 回應新增 `mdp_query` 欄位，表示查詢模組是否載入成功。

## OpenAI function calling

[`tools/openai-function-defs.json`](../tools/openai-function-defs.json) 提供 7 個
function schema（`mdp_list_blocks` / `mdp_get_block_meta` / `mdp_list_children` /
`mdp_read_block` / `mdp_search_blocks` / `mdp_resolve_xref` / `mdp_tree`），
任何 OpenAI agent 框架（Assistants API、自家 wrapper）都可直接載入。每個
description 都明示了「先 list 再 read」的呼叫順序，引導 model 走漸進式揭露。

## MCP server

[`mcp-server/mdp_mcp_server.py`](../mcp-server/mdp_mcp_server.py) 把同 7 個工具
暴露成 **MCP tools**，讓 Claude（Claude Desktop 或任何 MCP-aware client）直接做
漸進式揭露。一樣複用 `cli/python/query.py`，不重寫邏輯。

```bash
pip install -r mcp-server/requirements.txt

# 當 MCP server 跑（stdio transport，給 MCP client 連）
python mcp-server/mdp_mcp_server.py
```

Claude Desktop 設定（`claude_desktop_config.json`）：

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

**CLI 模式**：同樣 7 個工具不必接 MCP client 也能從命令列直接呼叫，方便測試與
腳本化：

```bash
python mcp-server/mdp_mcp_server.py --list-tools
python mcp-server/mdp_mcp_server.py --call mdp_list_blocks '{"path": "public/samples/decision-record.mdp.md", "depth": 1}'
python mcp-server/mdp_mcp_server.py --selftest
```

與 `/api/mdp/*` HTTP 端點（`path` 限定 `public/`）不同，MCP server 是**本機工具**，
接受任意可讀路徑——和 `mdp` CLI 一致。細節見
[`mcp-server/README.md`](../mcp-server/README.md)。

## 效能：單檔 parse cache

`query.py` / `query.mjs` 內建 **mtime + size 為 key 的 parse cache**。單檔 parse
本身 < 1ms，但 `/api/mdp/*` 與 MCP server 可能被互動式頻率打，每次重讀重 parse
是純浪費。cache 在檔案 mtime 或 size 改變的瞬間自動失效，呼叫端永遠看不到舊資料，
正常使用不需手動 invalidate。測試或長駐 process 要強制重讀可呼叫
`clear_cache()`（Python）/ `clearCache()`（Node）。

這是 Layer 3 跨檔索引（`.mdp-index.json`）之前的輕量優化：單檔場景用 cache 就夠，
不必先做完整索引層。

## 設計筆記

- **`title` 的推導**：優先用 `title:` metadata，否則取 body 第一行 prose
  （去掉 markdown 噪音、截斷至 80 字），最後 fallback 成 id 的人類化字串。
- **`line range` 的計算**：`read_block` 的 own-body 範圍 = 此 block header 到
  下一個 *任何* block header 之前；`include_children` 的子樹範圍 = 到下一個
  *同層或更淺* indent 的 block 之前。
- **未涵蓋（後續）**：Layer 3 跨檔索引（`.mdp-index.json`）、Layer 4 block 粒度
  編輯 API（`update_block_body` / `update_block_metadata` / `add_block` /
  `archive_block`）。本文件對應的是 P0（查詢 API + CLI）、P1（HTTP REST +
  OpenAI function defs）、P1.5（parse cache）與 P2（MCP server）。
