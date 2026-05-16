# Markdown+

> **Plain Markdown that AI agents read precisely and humans read beautifully.**
> No new dialect — just bullet-list blocks with `**#id**` headers and `key:value` metadata. Every Markdown+ document is also valid CommonMark.

[![Live demo](https://img.shields.io/badge/demo-zeabur-purple)](#deploy-to-zeabur) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](#local-development)

```markdown
- **#current-state** `type:state` `status:active` `updated:2026-05-13`
  目前 Auth v2 在 production 運作,refresh token 由 gateway 統一處理。

- **#sla-kpi** `type:kpi` `metric:API_SLA` `value:99.92` `unit:%` `target:99.95`
  API SLA 99.92%,目標 99.95%,本季因 5/3 outage 扣分 0.03 個百分點。

- **#auth-v1** `type:history` `status:deprecated` `superseded-by:current-state` `visibility:collapsed`
  Auth v1 已棄用,2026-02 全面遷移至 v2。
```

- 在 GitHub / Obsidian / VS Code → 看到的是清楚的 bullet list(graceful degradation)
- 在 Markdown+ viewer → 看到的是 section、status pill、KPI card、可摺疊歷史段、自動 TOC

## Why

AI agents 越來越多參與文件生產,但文件同時面對兩種讀者:

| 讀者 | 期待 |
|---|---|
| AI agent | 低冗餘、高語義密度、可局部讀取、穩定 ID |
| 人類 | 視覺層級、目錄、摺疊、圖表、互動 |

傳統做法走極端:
- 純 Markdown — 對 AI 友善但人類陽春
- HTML — 對人類漂亮但 AI 看到滿是 tag 噪音、tokens 暴漲
- 兩者混搭 — 兩邊都做不好

**Markdown+ 的立場是本體與投影分工**:source 是給 AI 的純 Markdown + 受控 metadata;HTML view 由 viewer 從 source 渲染。

### 實證數據(100 LLM calls,gpt-5.5)

| 格式 | tokens vs Markdown | 改寫時間 vs Markdown |
|---|---|---|
| Markdown | 1.00× | 1.00× |
| **Markdown+** | **1.46×** | **0.75×**(反而比生成 Markdown 快) |
| Medium HTML | 1.70× | 1.02× |
| Heavy HTML | **2.37×** | 1.49× |

「HTML 多耗 tokens 微乎其微」**經實證不成立**:Heavy HTML 比 Markdown 多 137%。Markdown+ 提供穩定中間選項。詳見 [docs/07-benchmark-results.md](docs/07-benchmark-results.md)。

## What's in this repo

```
markdown_plus/
│
├── server.py                    # 整合 server:serve public/ + /api/rewrite proxy
├── prompts/                     # LLM 改寫 prompts(server-side only)
│   ├── from_markdown.txt
│   └── from_html.txt
│
├── public/                      # 靜態網站根目錄(server.py 從這裡 serve)
│   ├── index.html               # 為何需要 Markdown+
│   ├── syntax.html              # 語法參考
│   ├── tutorial.html            # 六步教學
│   ├── playground.html          # 編輯 + 預覽 + LLM 改寫
│   ├── assets/                  # 網站 CSS
│   │   ├── site.css
│   │   └── playground.css
│   ├── lib/                     # 瀏覽器端的 Markdown+ 模組(validator + viewer)
│   │   ├── mdp-validator.mjs
│   │   ├── mdp-viewer.mjs
│   │   ├── viewer.css
│   │   └── viewer-runtime.js
│   └── samples/                 # 測試用 Markdown+ 文件
│       ├── kitchen-sink.mdp.md
│       ├── decision-record.mdp.md
│       ├── status-report.mdp.md
│       └── tutorial-install.mdp.md
│
├── cli/                         # 離線 CLI 工具(無 server,本機操作)
│   ├── python/
│   │   ├── validator.py
│   │   ├── viewer.py
│   │   ├── rewriter.py
│   │   ├── query.py             # Layer 2 block-query API(漸進式揭露)
│   │   └── mdp.py               # `mdp` CLI:list / tree / get / read / search / xref
│   └── node/
│       ├── rewriter.mjs
│       ├── query.mjs            # query.py 的 Node 對應
│       └── mdp.mjs              # `mdp` CLI 的 Node 對應
│
├── tools/                       # AI agent 整合資產
│   └── openai-function-defs.json  # block-query 的 OpenAI function calling schemas
│
├── mcp-server/                  # Markdown+ MCP server(block-query as MCP tools)
│   ├── mdp_mcp_server.py        # MCP stdio server + CLI 模式,複用 cli/python/query.py
│   ├── requirements.txt         # mcp>=1.2.0
│   └── README.md
│
├── skills/                      # Claude Skills source(canonical)
│   └── markdown-plus-author/    # 寫 / 改寫 Markdown+ 的 skill
│       ├── SKILL.md
│       ├── references/          # syntax / metadata / preservation / playbook ...
│       └── assets/evals/        # trigger / functional / regression evals
├── markdown-plus-author.skill   # 從 skills/markdown-plus-author/ 打包的 .skill zip
│
├── docs/                        # 完整文件
│   ├── 01-what-is-markdown-plus.md
│   ├── 02-syntax-reference.md
│   ├── 03-metadata-vocabulary.md
│   ├── 04-rewriting-playbook.md
│   ├── 05-code-fence-preservation.md
│   ├── 06-worked-examples.md
│   ├── 07-benchmark-results.md
│   ├── 08-block-based-query.md
│   ├── deploy-zeabur.md
│   └── CHANGELOG.md
│
│  ── 部署設定(放在 root,讓 PaaS 自動偵測) ──
├── requirements.txt             # openai>=1.60.0
├── Procfile                     # web: python server.py
├── runtime.txt                  # python-3.11
├── zeabur.json                  # Zeabur deployment config
├── Dockerfile                   # for Docker / Render / Fly
├── .gitignore
├── .dockerignore
├── LICENSE                      # MIT
└── README.md                    # this file
```

## Deploy to Zeabur

最簡部署:fork 本 repo → Zeabur 連 GitHub → 設 `OPENAI_API_KEY` env var → done.

詳細步驟:**[docs/deploy-zeabur.md](docs/deploy-zeabur.md)**

關鍵環境變數(在 Zeabur dashboard 的 Variables 設定):

| Key | 必填 | 預設 | 說明 |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key,僅在伺服器使用,**永不送到瀏覽器** |
| `REWRITER_MODEL` | optional | `gpt-5.4-mini` | 改寫用 model |
| `REWRITER_EFFORT` | optional | `none` | reasoning effort |
| `PORT` | (Zeabur 自動設) | `8000` | server 監聽 port |

## Local development

```bash
# 1. clone
git clone https://github.com/AllanYiin/markdown_plus.git
cd markdown_plus

# 2. install deps
pip install -r requirements.txt

# 3. set API key
# macOS / Linux:
export OPENAI_API_KEY=sk-...
# Windows PowerShell:
$env:OPENAI_API_KEY = "sk-..."

# 4. run
python server.py
# → http://localhost:8000
```

開瀏覽器到 `http://localhost:8000/playground.html` — Rewriter tab 點「改寫」即可呼叫 LLM。

不想用改寫器只看介紹/編輯/預覽 → 純靜態:`python -m http.server -d public 8000`(改寫按鈕會 disabled)。

## CLI tools

`cli/` 內含離線可用的 CLI 版本(Python 與 Node 分開):

```bash
# 驗證 Markdown+ 文件語法
python cli/python/validator.py public/samples/kitchen-sink.mdp.md
python cli/python/validator.py public/samples/kitchen-sink.mdp.md --json

# Markdown+ → HTML(單檔輸出,內嵌 CSS/JS)
python cli/python/viewer.py public/samples/kitchen-sink.mdp.md --out preview.html

# LLM 改寫(同 server.py 的邏輯,但純 CLI)
export OPENAI_API_KEY=sk-...
python cli/python/rewriter.py --from markdown input.md > output.mdp.md
python cli/python/rewriter.py --from html     input.html > output.mdp.md

# 或 Node 版本
npm install openai
node cli/node/rewriter.mjs --from markdown input.md > output.mdp.md
```

## Block-based query（漸進式揭露）

Markdown+ 的 block 結構讓 AI agent 不必把整份文件讀進 context——可以先調出
block manifest、再看單一 block 的 metadata、最後只讀真正需要的 block。對一份
100-block 的長文件回答「有哪些 open decision」，從 ~20,000 tokens 降到 ~800。

三種對外介面共用同一套 `cli/python/query.py` 邏輯：

```bash
# CLI:list manifest → 過濾 → 只讀命中的 block
python cli/python/mdp.py list   public/samples/decision-record.mdp.md --type task --status open
python cli/python/mdp.py read   public/samples/decision-record.mdp.md action-rollout
python cli/python/mdp.py tree   public/samples/decision-record.mdp.md
python cli/python/mdp.py search public/samples/decision-record.mdp.md turborepo
# Node 版:node cli/node/mdp.mjs list <doc> ...

# HTTP REST(server.py 啟動後):
curl "http://localhost:8000/api/mdp/list?path=samples/decision-record.mdp.md&type=task&status=open"
curl "http://localhost:8000/api/mdp/read?path=samples/decision-record.mdp.md&id=decision"
```

OpenAI agent 框架可直接載入 `tools/openai-function-defs.json`。給 Claude 用則跑
MCP server(同 7 個工具,也有 CLI 模式可獨立測試):

```bash
pip install -r mcp-server/requirements.txt
python mcp-server/mdp_mcp_server.py --list-tools          # CLI 模式:列出工具
python mcp-server/mdp_mcp_server.py --selftest            # CLI 模式:標準煙霧測試
python mcp-server/mdp_mcp_server.py                       # 當 MCP stdio server 跑
```

`query.py` / `query.mjs` 內建 mtime-based parse cache,`/api/mdp/*` 與 MCP server
被高頻打也不會重複 parse。完整說明見
**[docs/08-block-based-query.md](docs/08-block-based-query.md)**。

## Viewer enrichment(2026-05 起新增)

source 仍是純 Markdown,以下功能由 viewer 在 client-side 從 source 推導,**不修改 source、不打 LLM**。

### 1. SVG fence — 內聯渲染 + graph / code 切換

` ```svg ` 圍籬碼(<= 16 KB)會被 viewer 渲染成「graph 圖示 / code 原始碼」雙視圖元件,toolbar 顯示檔案大小,點按鈕切換。超過 16 KB 顯示警告 callout 並強制只顯示 source code,提示拆成外部 `.svg` 檔。
SVG 注入前自動去除 `<script>` tag 與 `on*=` event handler。

```markdown
- **#chart** `type:figure` `media:svg`

  *Figure: SLA 月度趨勢*

  \`\`\`svg
  <svg viewBox="0 0 320 120" xmlns="http://www.w3.org/2000/svg">
    <polyline points="50,40 130,56 210,70 290,72" fill="none" stroke="#0ea5e9" stroke-width="2"/>
    ...
  </svg>
  \`\`\`

  4 月 SLA 跌至 99.92%,低於目標。
```

→ 在 GitHub / Obsidian 看到的仍是合法 code fence(graceful degradation);在 viewer 看到的是渲染後的 SVG。

### 2. Mermaid fence — 同一 toggle 元件

` ```mermaid ` 圍籬碼透過同一 toggle 元件渲染,「graph」視圖呼叫 Mermaid 10 動態 import 從 CDN 渲染,「code」視圖顯示原始 mermaid source。

### 3. 自動關鍵詞抽取(無辭典中文 + 中英混合)

每個 block 的 body 內容會被 `KeywordExtractor` 抽出 top-N 關鍵詞,在 block header 下方以虛線 chip 顯示(`AUTO KEYWORDS`)。**演算法完全無辭典依賴**,瀏覽器端純 JS 即時計算:

| 步驟 | 做法 |
|---|---|
| 1. 文本清理 | 去掉 code fence / inline code / link / image / heading 標記 / block header 行 |
| 2. N-gram 枚舉 | CJK 連續字串 2 ~ 8 字;ASCII token(`Markdown+` / `block-based`)並行抓取 |
| 3. 內部凝固度 | PMI 對所有二分切分取最小值;`min_pmi ≥ 1.0` |
| 4. 左右自由度 | 左、右鄰字 Shannon 熵 各 ≥ 0.4(衡量該詞能否獨立使用) |
| 5. 詞頻過濾 | 出現次數 ≥ 2 |
| 6. 綜合排序 | `score = freq × min-PMI × min(left, right)-entropy`,降冪 |
| 7. 子字串抑制 | 較長的高分詞會擠掉它的子字串(若 freq 接近) |
| 8. 結構標籤前置 | 含 ` ```svg ` 的 block 永遠先放 `svg`;含 ` ```mermaid ` 的 block 先放 `mermaid` + 圖表類型(`sequenceDiagram` / `flowchart` / `classDiagram` / `gantt` / `graph` …) |

完全照「無詞典新詞發現」標準演算法實作(PMI + 左右熵雙閾值)。對 100-block 文件約毫秒級完成;ASCII token 走 log-frequency 當合成 cohesion(PMI-by-split 對拉丁字面意義不大)。

#### 自動 vs 手動 keywords

```markdown
- **#decision-canary** `type:decision` `status:accepted` \
  `keywords:canary,deployment,gradual-rollout`           ← 手動宣告(實線 chip)
  決定採 canary 部署...

- **#another-block** `type:note`                          ← 沒宣告 → viewer 自動抽(虛線 chip)
  本季 latency p99 降至 218ms...
```

**手動宣告永遠優先**;沒宣告時 viewer 才填入 auto chip。Playground sub-header 的「**寫入 keywords**」按鈕會把抽出的 auto 詞用 inline-code 寫進 source,confirm dialog 列出前 8 個 block 的建議讓你預覽,你可拒絕。

### 4. Playground 新增 sample

`samples/svg-medical-flow.mdp.md` 用一張 12 KB 的醫藥行銷說服流程 SVG 示範中型 inline SVG 場景。從 playground 右上「載入檔案」載入即可預覽。

## Markdown+ at a glance

- **Bullet-list block**:`- **#kebab-id** ` ``type:state`` ` ``status:active`` ` ...`
- **三習慣**:
  1. 每個 substantive section 是 bullet block
  2. 圖片、影片一律外部相對路徑(絕不 base64);SVG <= 16 KB 可用 ` ```svg ` fence 內聯,> 16 KB 仍須外部
  3. 每個 figure/table/chart/KPI 都有 prose companion 段
- **三原則**:
  1. **Graceful degradation** — source 在純 markdown viewer 仍可讀
  2. **Source for AI, projection for humans** — source 載語義,viewer 載視覺
  3. **No inline binary** — 二進位媒體一律外部路徑

完整語法見 [docs/02-syntax-reference.md](docs/02-syntax-reference.md)。

## What's served by the playground

進入 `playground.html` 後預設載入 `samples/kitchen-sink.mdp.md`(33 個 block 涵蓋全部 type)。其他內建範例可從「重新載入範例」切換,或用「載入檔案」按鈕從本機選 `.md` / `.mdp` 檔。

支援的 viewer 功能(全部在 browser 即時跑,**不需要 LLM call**):

| 功能 | 觸發條件 |
|---|---|
| 自動 TOC sidebar | 文件 ≥ 3 個 top-level block |
| Status pill | 任何 `status:` metadata |
| KPI card | `type:kpi` + value/target/delta |
| Gauge | `type:gauge` + min/max/zones |
| Dashboard grid | `type:dashboard` 容器內含多個 KPI |
| Variant tabs | 同層 siblings 共用 `variant-group:` |
| Dialogue bubbles | `type:dialogue` / `type:turn` + speaker |
| Mermaid 圖(graph/code 切換) | 含 ` ```mermaid ` fence |
| 內聯 SVG(graph/code 切換) | 含 ` ```svg ` fence,<= 16 KB |
| SVG 過大警示 | ` ```svg ` fence > 16 KB → 顯示 callout 與只顯示 code |
| 自動關鍵詞(無辭典 PMI + 左右熵) | 每個 block 都會自動產出;手動 `keywords:` 取代 auto |
| 「寫入 keywords」按鈕 | playground sub-header,把 auto 詞固化進 source |
| 摺疊歷史 | `type:history` 或 `visibility:collapsed` |
| Code copy 按鈕 | 每個程式碼區塊 |
| Block metadata footer | tags / superseded-by / related / source 等 |
| ASCII art rescue | 自動偵測 box-drawing 字元改用 `<pre>` |
| Plain markdown fallback | 沒有任何 `**#id**` block 時當純 markdown 渲染 |

只有「改寫」按鈕會打 `/api/rewrite` 呼叫 LLM。其他都是 client-side。

## Contributing

PRs welcome。重點改動方向:
- 新增 `type:` 種類 → 同步更新 viewer 投影規則 + `docs/03-metadata-vocabulary.md`
- 改 viewer 行為 → 在 `public/lib/mdp-viewer.mjs`(browser)與 `cli/python/viewer.py`(CLI)同步維護;`public/playground.html` 自包含一份 inline 副本,行為要對齊
- 改 validator 規則 → 在 `public/lib/mdp-validator.mjs` 與 `cli/python/validator.py` 同步
- 改 block-query 邏輯 → 在 `cli/python/query.py` 與 `cli/node/query.mjs` 同步;`server.py` 的 `/api/mdp/*` 直接複用 `query.py`
- 改 skill 內容 → 編輯 `skills/markdown-plus-author/`(canonical source),從這裡重打 `markdown-plus-author.skill` zip:
  ```bash
  cd skills && python -c "import zipfile, os; src='markdown-plus-author'; out='../markdown-plus-author.skill';\
  zf=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED); [zf.write(os.path.join(r,f), os.path.join(r,f).replace(os.sep,'/')) for r,_,fs in os.walk(src) for f in fs]; zf.close()"
  ```

## License

MIT — see [LICENSE](LICENSE).
