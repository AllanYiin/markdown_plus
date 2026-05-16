# 改寫 Playbook:Markdown / HTML → Markdown+

兩種輸入,兩套處理流程。共同前提:**保留事實,不增不刪**;**所有視覺裝飾留給 viewer**;**所有二進位媒體外部相對路徑化**;**code fence / ASCII tree / aligned art 一律 verbatim 保留**(詳見 `code-fence-preservation.md`)。

## 改寫前必過的紅線(hard checks before you start)

每次改寫**開始前**列出原文中的下列要素,並承諾在輸出中 1:1 保留:

| 要素類型 | 偵測方式 | 改寫時的義務 |
|---|---|---|
| ` ``` ` 或 ` ~~~ ` fence | grep `^[`~]{3,}` | fence 標記 + language + 內容逐字保留 |
| ASCII tree / 目錄 | 含 `│ ├ └ ─` 任一字元的多行內容 | 包進 ``` fence;若原文沒 fence 也要主動補一個 |
| Mermaid / vega-lite / DSL | fence 含已知 language tag | 整段保留,額外加 `chart-type:` / `diagram-type:` metadata |
| Aligned art / 表格仿排 | 多行固定欄寬靠空白對齊 | 包進 ``` fence |
| Inline `<svg>` / `<script>` / base64 data URI | grep 對應字串 | **停下來問用戶**,不可自動處理 |


## 一、Plain Markdown → Markdown+

### Phase 1:結構盤點
1. 讀全文,列出所有 H2 / H3 章節,當成候選 top-level block。
2. 判斷 H1 是否該保留(通常保留為文件標題)。
3. 找出散在文中的圖、表、code fence、callout,記下它們屬於哪個章節。
4. 若文件沒有清楚 H2 章節(只有一大段散文),停下來問用戶:這份文件是否真的需要 Markdown+?還是純 markdown 就夠?

### Phase 2:指派 ID 與 type
針對每個候選 block:
1. **ID**:用語義鎖死的 kebab-case (`current-state`、`auth-v1-migration`、`q1-revenue`)。不要用 `block1`、`section-a`。
2. **type**:對照 `metadata-vocabulary.md` 的 closed list。最常見:
   - 描述現況 → `type:state`
   - 歷史 / 棄用 → `type:history`
   - 決策紀錄 → `type:decision`
   - 規格 / 設計 → `type:spec`
   - 待辦 → `type:task`
   - 圖 / 表 / 圖表 → `type:figure` / `table` / `chart`

### Phase 3:抽 metadata
從原文線索抽取:
- 日期 → `updated:`
- 「已棄用」「廢棄」「v1 (legacy)」→ `status:deprecated` + `superseded-by:`
- 「待辦」「TODO」「action item」→ `status:open` 或 `status:blocked`
- 標籤化的詞 (技術名、團隊名) → `tags:[namespace:value]`

**找不到日期**:不要猜,用 `updated:unknown` 或省略該欄。

### Phase 4:寫 block
按文件原順序,把每個章節轉成 bullet-list block:

```markdown
原文:
## Current auth state
We use Auth v2. Gateway handles refresh.

轉成:
- **#current-state** `type:state` `status:active` `updated:2026-05-13`
  We use Auth v2. Gateway handles refresh.
```

H2 的 heading 文字通常變成 block 的 title 或被 ID 替代。若想保留可讀標題,可在 body 開頭寫 `### <Title>` (block 內 H3),但通常 ID + viewer 渲染就夠。

### Phase 5:處理嵌入內容
- **表格**:上方加 `*Table: ...*` caption。若 > 30 列,搬到 CSV 並改用 `data-source:`。
- **code fence**:上方加 `*Listing: ...*` caption(可選,純技術片段免)。
- **圖片**:確認 path 是相對路徑;若是絕對路徑或 URL,改成 `./assets/<name>.<ext>` 並把檔案搬到對應位置。
- **callout** (`> NOTE` / `> WARNING`):改成 GFM alert 語法 (`> [!NOTE]`)。

### Phase 6:加 prose companion
對每個 figure / chart / table / video block,在最後加一段散文(1-3 句)說明:
- 看到什麼
- 結論是什麼

### Phase 7:跑驗證(SKILL.md 的 output_contract)

## 二、HTML → Markdown+

更難,因為 HTML 同時混了內容、樣式、互動。**任務本質是「剝掉投影層,只留語義層」**。

### Phase 1:HTML 預掃描
跑這幾項偵測:

| 偵測項 | 動作 |
|---|---|
| `<script>` 標籤 | **整段刪除**(投影行為,不是內容) |
| `<style>` 標籤 | **整段刪除** |
| `class=""` `style=""` `id=""` | 刪除 attribute(除非 id 是錨點,改寫成 block id) |
| `<nav>` `<header>` `<footer>` | 通常刪除(viewer 會重建);若內含資訊性內容(版權聲明等)移到對應 block |
| `<div>` `<span>` 純包裝 | 解包,只留 inner text |
| `<aside>` 補充內容 | 改成 `type:note` 或 `type:issue` block |
| `<article>` `<section>` | 通常各成一個 top-level block |
| `<table>` | 轉 markdown 表格,>30 列拆 CSV |
| `<img src="...">` | 取 src,如為 base64 → **停下來問用戶** |
| `<img src="data:...;base64,...">` | **停。報告。要求外部檔案** |
| `<svg>` inline | **停。要求改為外部 SVG 檔** |
| `<video>` / `<audio>` | 取 src,改成 markdown 連結加 `type:figure` `media:video/audio` |
| 巢狀 chart container(Highcharts、Chart.js) | 取出 data + config,寫到外部檔案 |

### Phase 2:抽取語義
從 cleaned HTML:
1. 找 `<h1>` → 變成文件 H1
2. 找 `<h2>` → 變成 top-level block(配對 `type:` 由內容決定)
3. 找 `<h3>` 等 → 變成 child block 或 block body 內部 heading

### Phase 3:對應到 block type
HTML semantic tag → Markdown+ `type:` 對照:

| HTML 元素 | 預設 type |
|---|---|
| `<article>` | (整篇變一份文件) |
| `<section>` | `type:state` / `spec` / `record` (看內容) |
| `<aside class="warning">` | `type:issue` 或 `type:note` |
| `<aside class="info">` | `type:note` |
| `<details>` (含 `<summary>`) | `type:history` 或 `visibility:collapsed` |
| `<figure>` + `<figcaption>` | `type:figure`,caption 變 `*Figure: ...*` |
| `<table>` + `<caption>` | `type:table`,caption 變 `*Table: ...*` |
| `<blockquote cite="...">` | block quote + `source:` metadata |
| `<dl>` (description list) | 改成 table 或 bullet list |
| `<time datetime="...">` | 抽進 `updated:` |
| `<address>` | `author:` / `owner:` |

### Phase 4:抽 metadata
從 HTML 信號抽取:
- `<time datetime="2026-05-13">` → `updated:2026-05-13`
- `<aside class="warning deprecated">` → `status:deprecated`
- `data-status="active"` → `status:active`
- `class="kpi"` + 內含大數字 → `type:kpi`,從 inner text 抽 `value:`
- `<details>` default closed → `visibility:collapsed`

### Phase 5:處理「重 UI 結構」
如果 HTML 含 navbar、sidebar、卡片網格、tab、accordion、modal 等:
- **navbar / sidebar / footer 等 layout 元件**:全部刪除,viewer 會重建
- **卡片網格**:每張卡轉成一個 sibling block,共用 parent
- **tab UI**:每個 tab pane 轉成 sibling block 共用 `variant-group:`
- **accordion**:每個 panel 轉成 block,適用時加 `visibility:collapsed`
- **modal / overlay 內容**:整段轉成 `type:note` block 或 `visibility:hidden`
- **scroll-spy / sticky nav**:刪除,viewer 會從 manifest 自動產

### Phase 6:特別注意 — KPI / Dashboard
HTML dashboard 常見 pattern:
```html
<div class="kpi-card">
  <div class="metric-name">MRR</div>
  <div class="metric-value">$1.2M</div>
  <div class="metric-target">Target: $1.5M</div>
  <div class="metric-delta">+12%</div>
</div>
```

轉成:
```markdown
- **#mrr-kpi** `type:kpi` `metric:MRR` `value:1.2M` `target:1.5M` `delta:+12%`
  MRR $1.2M,target $1.5M,Q1 達成 80%,較上季 +12%。
```

注意:**必須加 prose 段**(`MRR $1.2M, target $1.5M...`),因為 HTML 卡片有視覺,markdown+ 沒有,prose 要補足。

### Phase 7:處理連結
- 內部錨點 `<a href="#section-1">` → 改成 `[text](#section-1)`,確認 target block id 存在
- 外部連結保留
- `<a href="javascript:...">` → **刪除**(viewer 不應信任 source 的 JS)

### Phase 8:驗證
跑 SKILL.md 的 output_contract checklist。HTML 改寫特別要驗:
- [ ] 沒有殘留 `<script>` `<style>` `<svg>` (inline)
- [ ] 沒有 `class=` `style=` `data-*` (除非 `data-source:` 已轉成 metadata)
- [ ] 沒有 base64 / data URI
- [ ] 所有 KPI / dashboard 都有 prose companion
- [ ] 所有原 `<table>` 都有 `*Table: ...*` caption

## 三、共通的判斷邊界

### 何時不該改成 Markdown+?
- 原文太短(< 3 個有意義章節)— 直接保留純 markdown
- 原文是純散文 (essay / 文學) — 結構化會破壞文體
- 原文是純參考表 / cheat sheet — markdown table 就夠
- 原文是 transient note(聊天記錄、暫時備忘)— 不值得 metadata 成本

### 何時要主動拆 block?
- 一個 block body 超過 ~30 行 → 拆 sub-block
- 一個 block 內混了多種 type 的內容 → 拆
- 兩段不同生命週期的內容寫在一起 (現況 + 歷史) → 拆,且 history 加 `visibility:collapsed`

### 何時要主動合 block?
- 兩個 block 都 < 5 行且語義黏在一起 → 合
- 兩個 block 是同一決策的 part of → 合或建立 parent

## 四、與用戶互動

只在這些情況問用戶:
1. **input 含 base64 媒體** → 詢問外部檔案路徑或請用戶 extract
2. **input 含巨型 chart spec** → 詢問是否拆外部
3. **input 結構過於混亂** → 詢問希望的 block 切分方式
4. **type 推斷高度不確定** → 列 2-3 個候選請用戶選

其他情況直接做。不要為了確認小細節中斷流程。

## 五、輸出格式

最終只輸出 Markdown+ 文件本體,**不要**:
- 解釋你做了什麼
- 列出改了哪些東西
- 加 commentary 段落
- 包進 code fence

若要交付改寫摘要,用戶會明確要求。
