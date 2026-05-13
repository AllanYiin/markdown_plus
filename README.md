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
│   │   └── rewriter.py
│   └── node/
│       └── rewriter.mjs
│
├── docs/                        # 完整文件
│   ├── 01-what-is-markdown-plus.md
│   ├── 02-syntax-reference.md
│   ├── 03-metadata-vocabulary.md
│   ├── 04-rewriting-playbook.md
│   ├── 05-code-fence-preservation.md
│   ├── 06-worked-examples.md
│   ├── 07-benchmark-results.md
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

## Markdown+ at a glance

- **Bullet-list block**:`- **#kebab-id** ` ``type:state`` ` ``status:active`` ` ...`
- **三習慣**:
  1. 每個 substantive section 是 bullet block
  2. 圖片、影片、SVG 一律外部相對路徑(絕不 base64)
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
| Mermaid 圖 | 含 ```mermaid``` fence |
| 摺疊歷史 | `type:history` 或 `visibility:collapsed` |
| Code copy 按鈕 | 每個程式碼區塊 |
| Block metadata footer | tags / superseded-by / related / source 等 |
| ASCII art rescue | 自動偵測 box-drawing 字元改用 `<pre>` |
| Plain markdown fallback | 沒有任何 `**#id**` block 時當純 markdown 渲染 |

只有「改寫」按鈕會打 `/api/rewrite` 呼叫 LLM。其他都是 client-side。

## Contributing

PRs welcome。重點改動方向:
- 新增 `type:` 種類 → 同步更新 viewer 投影規則 + `docs/03-metadata-vocabulary.md`
- 改 viewer 行為 → 在 `public/lib/mdp-viewer.mjs`(browser)與 `cli/python/viewer.py`(CLI)同步維護
- 改 validator 規則 → 在 `public/lib/mdp-validator.mjs` 與 `cli/python/validator.py` 同步

## License

MIT — see [LICENSE](LICENSE).
