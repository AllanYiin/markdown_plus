# Markdown+ 語法完整參考

本檔是 Markdown+ source 的權威語法定義。所有 source 在 vanilla CommonMark viewer 開啟必須仍為合法可讀內容。

## 1. 文件骨架

```markdown
# <文件標題>

<一段短引言,純散文,沒有 block 語法>

- **#<top-level-block-id>** `type:<value>` [<metadata>]
  <block body, 縮排 2 spaces>

- **#<another-top-level-block>** `type:<value>` [<metadata>]
  <block body>

  - **#<child-block>** `type:<value>` [<metadata>]
    <nested block body, 縮排 4 spaces>
```

規則:
- H1 (`#`) 整份文件**只能有一個**,作為文件總標題。
- H1 之後可接 0~1 段純散文引言。
- 接下來全部是 bullet-list 開頭的 block。
- 整份文件**不允許**在 block 之外出現 H2 / H3 — 章節邊界由 block 承擔,不由 heading 承擔。
- block body 內部可自由用 H3 / H4(很少需要)、清單、表格、code fence、blockquote 等。

## 2. Block header 語法

完整形式:

```
- **#<id>** `<key>:<value>` `<key>:<value>` ... [`<key>:<value>` ...]
```

組成:
| 元件 | 規則 | 範例 |
|---|---|---|
| Bullet 前綴 | `- ` (dash + space) | `- ` |
| ID | `**#<kebab-case>**`,粗體包 hashtag + kebab-case id | `**#current-state**` |
| Metadata | inline code 的 `key:value`,空格分隔多個 | `` `type:state` `` `` `status:active` `` |

範例:
```markdown
- **#mrr-kpi** `type:kpi` `metric:MRR` `value:1.2M` `target:1.5M` `delta:+12%` `period:2026-Q1`
```

純 markdown viewer 看到:
- 圓點 bullet
- 粗體 `#mrr-kpi`(類似 hashtag 錨點)
- 一連串 monospace inline code(類似 badge)

Markdown+ viewer 解析後:
- `<section id="mrr-kpi" data-type="kpi">`
- 標題列右側顯示 status pill 與 updated 時間
- body 內容渲染成 KPI card

## 3. ID 命名規則

- 一律 **kebab-case**(小寫字母 + 數字 + 連字號)
- 在**同一份文件內必須唯一**
- 不可以以連字號開頭或結尾
- 不可以包含中文、空格、底線
- 推薦長度 2~5 個詞,語義明確
- ID 一旦對外公開(寫進 `superseded-by:` / `related:` / `parent:`),**禁止任意改名** — 真要改必須先更新所有引用

✅ Good:`current-state`, `q1-revenue`, `auth-v1-deprecation`, `gateway-spec`
❌ Bad:`Block1`, `_state`, `current state`, `現況區`, `block-`

## 4. Metadata 寫法

每個 key 寫成一個 inline code:`` `key:value` ``。

### 4a. 單一值
```markdown
`type:state`
`status:active`
`updated:2026-05-13`
```

### 4b. 列表值
列表用 `[a,b,c]` 表達,**不加空格**:
```markdown
`tags:[auth,gateway,security]`
`related:[auth-v1,gateway-spec]`
```

### 4c. 含空格或特殊字元的值
若 value 含空格或冒號,改用底線或 kebab-case;不要在 inline code 內用引號:
- ✅ `metric:monthly-recurring-revenue`
- ❌ `` `metric:"Monthly Recurring Revenue"` ``

### 4d. 多個 metadata 排序
建議順序:**identity → lifecycle → visibility → taxonomy → type-specific**。
範例:
```markdown
- **#auth-v1** `type:history` `status:deprecated` `superseded-by:current-state` `updated:2026-02-15` `visibility:collapsed` `tags:[auth,archive]`
```

不強制,但 viewer 顯示通常依此順序排在標題列。

## 5. 父子關係(縮排規則)

Markdown+ 用 **bullet list nesting** 表達父子。

```markdown
- **#parent** `type:document`
  Parent body content (indented 2 spaces).

  - **#child-1** `type:section`
    Child body (indented 4 spaces total from line start).

    - **#grandchild** `type:note`
      Grandchild body (indented 6 spaces).

  - **#child-2** `type:section`
    另一個子 block。
```

縮排規則:
- **必須用 2-space 縮排**(不允許 tab、不允許 4-space)
- block body 跟 block header 的縮排相同(都比 bullet 多 2 spaces)
- 子 block 整體比父 block bullet 縮排 2 spaces

可選:也可在子 block metadata 加 `parent:<parent-id>` 作為冗餘錨定。當需要扁平排列或跨層級引用時可用。

## 6. Caption 寫法

table / code fence / image / video / audio / chart / svg 上方緊鄰一行 italic caption:

```markdown
*Table: Q1 月度營收(USD,單位 K)*

| 月份 | 企業 | 消費者 |
|------|------|--------|
| Jan  | 320  | 180    |
```

Caption 種類(都用 italic):
- `*Table: ...*` — 表格
- `*Figure: ...*` — 圖片 / SVG / 圖表
- `*Listing: ...*` — 程式碼
- `*Chart: ...*` — 資料視覺化
- `*Demo: ...*` — 影片 / 互動演示

規則:
- **不寫死編號**(`*Table 1: ...*` 是錯的)
- viewer 依 block manifest 順序自動編號
- caption 必須**緊鄰**目標物(中間不可有空行)

## 7. Prose Companion 規則

每個含視覺 / 數據資料的 block 必須有 prose companion paragraph:

```markdown
- **#q1-revenue-table** `type:table` `sortable:true`

  *Table: Q1 月度營收(USD,單位 K)*

  | 月份 | 企業 | 消費者 | 合計 |
  |------|------|--------|------|
  | Jan  | 320  | 180    | 500  |
  | Mar  | 540  | 200    | 740  |

  Q1 合計 1,845K,3 月較 1 月成長 47%,企業方案佔比從 64% 升到 73%。
```

最後那段散文就是 prose companion,寫進 source 才算合格。

Prose companion 寫作要點:
1. 至少 1 句,不超過 3 句
2. 必須包含**結論**(不只是「這是表格」)
3. 數字要能對應到表格 / 圖中
4. 語氣與文件主體一致

## 8. 媒體引用(必要外部路徑)

### 8a. 圖片
```markdown
- **#auth-arch-diagram** `type:figure` `alt:auth-flow-architecture`

  *Figure: 登入流程三層架構*

  ![Auth flow](./diagrams/auth-flow.png)

  圖中三條 token 路徑:browser 走 httpOnly cookie、mobile 走 signed JWT、server-to-server 走 mTLS。
```

### 8b. SVG

SVG 是文字格式,允許在 ` ```svg ` code fence 內 inline,但有大小上限:

| SVG 大小 | 寫法 | viewer 行為 |
|---|---|---|
| ≤ 16 KB | ` ```svg ... ``` ` inline fence | 渲染圖 + `graph` / `code` 雙視圖 toolbar |
| > 16 KB | 外部檔 `![alt](./diagrams/<name>.svg)` | 一般圖片載入 |

````markdown
- **#sla-trend** `type:figure` `media:svg`

  *Figure: API SLA 月度趨勢*

  ```svg
  <svg viewBox="0 0 320 120" xmlns="http://www.w3.org/2000/svg">
    <polyline points="50,40 130,56 210,70 290,72" fill="none" stroke="#0ea5e9" stroke-width="2"/>
    ...
  </svg>
  ```

  4 月 SLA 跌至 99.92%,低於 99.95% 目標線。
````

注意事項:
- **絕對禁止** raw `<svg>` 直接寫在 markdown 段落或 HTML 容器內 — 必須包進 ` ```svg ` fence 或外部檔。
- viewer 注入前自動移除 `<script>` 與 `on*=` event handlers,結構標記(`<defs>`、`<style>`、`<marker>`、`<filter>`)保留。
- block 自動帶 `keywords:svg`(viewer 投影);手寫 metadata 不需重複宣告。

### 8c. 影片
```markdown
- **#onboarding-demo** `type:figure` `media:video` `duration:2m30s` `transcript:./transcripts/onboarding.txt`

  *Demo: onboarding 從註冊到第一次 API call*

  [▶ onboarding.mp4](./media/onboarding.mp4)

  影片章節:0:00 註冊、0:45 建立 project、1:30 第一次 API call。
```

### 8d. 大型 chart spec
**外部檔案**:
```markdown
- **#q1-revenue-chart** `type:chart` `chart-type:vega-lite` `data-source:./data/q1.csv`

  *Chart: Q1 月度營收*

  ![Q1 revenue](./charts/q1-revenue.vl.json)

  3 月較 1 月 +47%,主要來自 enterprise 新簽 23 筆。
```

### 8e. 小型 chart spec(可 inline fence)
Mermaid-style fence,**僅在 spec 不超過 ~80 行時**使用:

````markdown
- **#user-flow** `type:diagram` `diagram-type:mermaid`

  *Figure: 註冊流程*

  ```mermaid
  flowchart TD
      A[Landing] --> B[Sign up]
      B --> C{Email verified?}
      C -->|Yes| D[Onboarding]
      C -->|No| E[Resend]
  ```

  email verification 是最大 drop-off 點(38%)。
````

## 9. 表格增強

### 9a. 標準表格
標準 GFM 表格即可,無需額外語法。

### 9b. Cell-level 狀態 / 趨勢
用 inline code 慣例(與 block metadata 同一套):
```markdown
| 服務    | Status              | p99   | Trend       |
|---------|---------------------|-------|-------------|
| auth    | `status:healthy`    | 42ms  | `trend:down`|
| billing | `status:degraded`   | 380ms | `trend:up2` |
```

### 9c. Row grouping
```markdown
| 區域 / 服務     | p99   |
|-----------------|-------|
| **— US-East —** |       |
| auth            | 42ms  |
| billing         | 380ms |
| **— EU-West —** |       |
| auth            | 58ms  |
```

### 9d. 外部 CSV
表格 > 30 列:
```markdown
- **#sales-detail** `type:table` `data-source:./data/sales-detail.csv` `sortable:true` `pagination:50`

  *Table: 詳細銷售明細(478 筆)*

  資料 `./data/sales-detail.csv`,欄位:date / region / plan / amount / customer_id。
  Top 3 region:US-East 35% / EU-West 28% / APAC 19%。
```

## 10. Callout / Admonition

直接用 GFM alert 語法,Markdown+ viewer 渲染成 colored callout box:

```markdown
> [!NOTE]
> 注意事項...

> [!WARNING]
> 警告事項...

> [!IMPORTANT]
> 重要訊息...

> [!TIP]
> 提示...

> [!CAUTION]
> 嚴重警告...
```

## 11. KPI / Card / Gauge / Targets / Dashboard

由 `type:` 與專屬 metadata 控制,範例見 `references/worked-examples.md`。Key 規則:
- `type:kpi` 必有 `value:` `target:` `delta:` 與 prose 段
- `type:gauge` 必有 `value:` `min:` `max:` `target:` `zones:`
- `type:targets` 用標準表格 + 每列含 `status:` cell
- `type:dashboard` 是容器,內含多個 `type:kpi` siblings,viewer 自動 grid

## 12. 對話 / Dialogue

```markdown
- **#interview-2026-05-10** `type:dialogue` `participants:[ann,bob]`

  - **#turn-1** `speaker:ann` `time:14:02`
    > 你覺得新版 API 最大的痛點?

  - **#turn-2** `speaker:bob` `time:14:02`
    > 錯誤訊息太抽象,trace ID 也沒回傳。
```

純 markdown:nested list + blockquote。Viewer:左右氣泡。

## 13. Tabbed / Variant 聚合

不寫 `:::tabs` directive。改用 sibling block 共用 `variant-group:`:

```markdown
- **#install-mac** `type:step` `variant-group:install` `variant:mac`
  ```bash
  brew install foo
  ```

- **#install-linux** `type:step` `variant-group:install` `variant:linux`
  ```bash
  apt install foo
  ```

- **#install-windows** `type:step` `variant-group:install` `variant:windows`
  ```bash
  scoop install foo
  ```
```

純 markdown:三個並排 block(全可見)。Viewer:自動 tab。

## 14. Cross-link

```markdown
- **#auth-v1** `type:history` `status:deprecated` `superseded-by:current-state` `related:[gateway-spec,migration-2026-q1]`
```

`superseded-by:` 與 `related:` 都接 block id。Viewer 渲染為可點擊跳轉。

## 15. 禁止清單(hard rules)

| 禁止項 | 替代方案 |
|---|---|
| `:::block` / `:::section` 等 fenced div | 改用 bullet list block |
| Raw HTML (除 `<br>` `<hr>` `<sub>` `<sup>`) | 由 viewer 渲染 |
| `<script>` / `<style>` / `data-*` 在 source | 留給 viewer |
| `class=""` / `style=""` | 留給 viewer |
| Inline `data:image/...;base64,...` | 改用 `./relative/path` 外部檔案 |
| Raw `<svg>` 寫在 markdown 段落或 HTML 容器內 | 包進 ` ```svg ` fence(≤ 16 KB)或外部檔 `![alt](./path.svg)` |
| ` ```svg ` fence > 16 KB | 拆成外部 `./diagrams/<name>.svg` |
| 巨型 inline JSON chart spec(>80 行) | 拆到 `./charts/*.json` |
| 巨型 inline 表格(>30 列) | 拆到 `./data/*.csv` |
| Caption 寫死編號(`Figure 1:`) | 只寫 `*Figure: ...*`,讓 viewer 編號 |
| 自由文字 `type:` 值 | 改用受控字彙表或 `x-` prefix |

## 16. 自動關鍵詞抽取(viewer 投影,不影響 source)

每個 block 若未宣告 `keywords:`,viewer 會用**純統計、無辭典依賴**演算法即時抽出 top-N 關鍵詞,以虛線 chip 顯示。**source 不會被自動修改**;playground 提供「寫入 keywords」按鈕讓使用者顯式 persist。

演算法摘要(完全照「無詞典新詞發現」標準):

1. **文本清理** — 剝除 code fence / inline code / image / link / heading / block header
2. **N-gram 枚舉** — CJK 連續字串 2~8 字 + ASCII token `[A-Za-z][A-Za-z0-9+\-]*` 並行
3. **內部凝固度 PMI** — `PMI(x,y) = log(P(xy)/(P(x)P(y)))`,對所有二分切分取 **最小值** ≥ 1.0
4. **左右自由度** — 左、右鄰字 Shannon 熵各 ≥ 0.4(衡量詞能否獨立)
5. **詞頻過濾** — ≥ 2 次
6. **綜合排序** — `score = freq × min-PMI × min(L, R)`,降冪
7. **子字串抑制** — 長詞 freq 接近時擠掉子字串
8. **結構標籤前置** — 含 ` ```svg ` → `svg`;含 ` ```mermaid ` → `mermaid` + 圖表類型(從 fence 第一行抓)

預設參數:`min_len=2, max_len=8, min_freq=2, min_pmi=1.0, min_entropy=0.4`,全域 topK=80、每 block top-5。

**何時需要手動宣告 `keywords:`**:
- auto 抽取結果不準(block 用了統計訊號抓不到的特殊術語)
- 下游 agent 依 keyword 做查詢,需要精確控制
- 單檔短文(語料太少,統計信號弱)

**何時不該手動宣告**:
- block 內含 ` ```svg ` / ` ```mermaid ` → 結構標籤會自動加,不要重複
- 內容語義詞 viewer 抓得到 → 留白讓 auto 跑

範例(混合宣告):

```markdown
- **#decision-canary** `type:decision` `status:accepted` `keywords:canary,deployment,gradual-rollout`
  本決策...                                                  ← 手動宣告生效,實線 chip

- **#flow-diagram** `type:diagram`                            ← 未宣告
  ```mermaid
  flowchart TD
      A --> B
  ```
  本流程...                                                  ← auto 帶 `mermaid` + `flowchart` + 內容詞,虛線 chip
```
