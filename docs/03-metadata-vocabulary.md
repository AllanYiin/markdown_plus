# Metadata 受控字彙表與寫作指引

讓 AI / 人類都讀得順的關鍵不在於「多寫 metadata」,而在於 **每個 key 都有明確語義、每個 value 都來自受控集合、metadata 與 prose 互不矛盾**。

## 1. 寫好 metadata 的五條原則

### 原則 1:語義 over 樣式
metadata key 描述**這個 block 是什麼**,不描述它**長什麼樣**。
- ✅ `type:decision` `status:accepted`
- ❌ `style:blue-card` `width:full`

### 原則 2:Closed vocabulary
`type:` / `status:` / `trend:` / `visibility:` / `priority:` 都是 closed list。需要擴充用 `x-` 前綴 (例如 `type:x-endpoint`),並且必須在 prose 解釋它的 fallback 投影。

### 原則 3:Compact, declarative summary
`summary:` 與 prose companion 都應該**一句話宣告事實**,不要寫成段落。AI pre-read 用它判斷要不要展開全文。

### 原則 4:Metadata 數字 ↔ prose 數字必須一致
`type:kpi` 的 `value:1.2M` 跟 prose 段裡的 `MRR $1.2M` 必須一致;改一個就改另一個。否則 AI 摘要會出現自相矛盾。

### 原則 5:Tag 用 namespace
`tags:` 不是自由標籤雲。建議導入 `domain:` / `team:` / `module:` / `status:` 等 namespace,讓 tag 可分群:
- `tags:[domain:auth, team:platform, module:gateway]`
- 而非 `tags:[auth, platform, gateway, internal-only, 2026]` 這種扁平亂堆

## 2. 受控字彙表

### 2a. `type:` (block 主類型)

closed list,**禁止**自由擴充。需要新 type 必須先加進這份字彙表,或臨時用 `x-` prefix。

| Type | 用途 | 預設 HTML 投影 |
|---|---|---|
| `document` | 整份文件 root (極少用,通常省略 root 由 H1 承擔) | `<article>` |
| `state` | 描述當前事實 / 現況 | `<section>` |
| `history` | 已經不適用的歷史記錄 | `<details>` (default closed) |
| `decision` | 決策紀錄 | `<aside class="decision">` |
| `record` | 一次性事件紀錄(會議、incident) | `<section class="record">` |
| `issue` | 待解問題 / blocker | `<aside class="issue">` |
| `note` | 補充說明 / 旁註 | `<aside class="note">` |
| `spec` | 規格 / 技術說明 | `<section>` |
| `task` | 待辦事項 / action item | `<section class="task">` |
| `reference` | 連結 / 外部資源彙整 | `<section class="reference">` |
| `figure` | 圖片 / SVG / 示意圖 | `<figure>` |
| `table` | 表格 (尤其需要 sortable / searchable 時) | `<figure class="table">` |
| `chart` | 資料視覺化 | `<figure class="chart">` |
| `kpi` | 單一關鍵指標卡 | `<section class="kpi">` |
| `card` | 通用 UI card | `<section class="card">` |
| `gauge` | 量表 (有 min/max/target/zones) | `<section class="gauge">` |
| `targets` | actual vs target 比較表 | `<section class="targets">` |
| `dashboard` | KPI grid 容器 | `<section class="dashboard">` |
| `dialogue` | 對話容器 | `<section class="dialogue">` |
| `turn` | 對話 turn (在 dialogue 內) | `<div class="turn">` |
| `step` | 教學 / runbook 步驟 | `<section class="step">` |
| `diagram` | 流程圖 / 架構圖 (通常 Mermaid) | `<figure class="diagram">` |

### 2b. `status:`

| Status | 用途 |
|---|---|
| `draft` | 草稿,未完成 |
| `active` | 當前有效 |
| `proposed` | 提案中(decision) |
| `accepted` | 已接受 (decision) |
| `rejected` | 已駁回 (decision) |
| `superseded` | 已被取代 (必須有 `superseded-by:`) |
| `deprecated` | 已棄用 (必須有 `superseded-by:`,通常配 `visibility:collapsed`) |
| `archive` | 歸檔 |
| `healthy` | 健康 (service status) |
| `degraded` | 降級 (service status) |
| `down` | 中斷 (service status) |
| `on-track` | 進度符合 (targets / task) |
| `behind` | 進度落後 (targets / task) |
| `exceeded` | 超標 (targets / task) |
| `done` | 完成 (task) |
| `blocked` | 阻塞 (task / issue) |
| `open` | 未處理 (issue) |
| `closed` | 已關閉 (issue) |

### 2c. `trend:`

用於 table cell,viewer 渲染成箭頭 + 顏色。

| Value | 含義 |
|---|---|
| `up` | 上升 (中等) |
| `up2` | 強烈上升 |
| `down` | 下降 (中等) |
| `down2` | 強烈下降 |
| `flat` | 持平 |

「好壞」由 viewer 與 context 決定 (例如 `trend:down` 對 latency 是好,對 revenue 是壞)。需要明確語義時再加 prose 補充。

### 2d. `visibility:`

| Value | 含義 |
|---|---|
| (省略) | default visible |
| `collapsed` | viewer 預設摺疊 (`<details>` closed) |
| `hidden` | viewer 不顯示但保留在 source (用於 archive / 半棄用) |

### 2e. `priority:`

| Value | 含義 |
|---|---|
| `critical` | 必讀 |
| `high` | 高優先 |
| `normal` | 預設 (省略時即 normal) |
| `low` | 補充資訊 |

AI pre-read 應優先讀 critical / high。

### 2f. `audience:`

| Value | 含義 |
|---|---|
| `everyone` | 公開內容 (省略時預設) |
| `internal` | 僅內部 |
| `team` | 僅該團隊 |
| `executive` | 給高階主管 |
| `engineer` | 給工程師 |

viewer 可依登入身份過濾。

## 3. Metadata key 全清單

按用途分群。每個 key 對應到的 source 撰寫慣例與 viewer 行為都寫死,避免漂移。

### Identity (身份)
| Key | 必需 | 規則 |
|---|---|---|
| `type` | ✅ | closed vocabulary,見 2a |
| `parent` | optional | 父 block id (冗餘錨定,當縮排父子不夠明確時) |
| `order` | optional | 同層 siblings 順序 (數字,小→大) |

### Lifecycle (生命週期)
| Key | 規則 |
|---|---|
| `status` | closed vocabulary,見 2b |
| `updated` | ISO date `YYYY-MM-DD` |
| `valid-until` | ISO date,過期後 viewer 應標 stale |
| `superseded-by` | 接受替代者的 block id (status:deprecated / superseded 必填) |
| `created` | ISO date (極少需要) |

### Visibility / Priority
| Key | 規則 |
|---|---|
| `visibility` | 見 2d |
| `priority` | 見 2e |
| `audience` | 見 2f |

### Taxonomy
| Key | 規則 |
|---|---|
| `tags` | `[a,b,c]`,推薦用 namespace |
| `category` | 單值,文件級分類 |

### Source / Ownership
| Key | 規則 |
|---|---|
| `source` | 內容來源 (URL / file path / event id) |
| `author` | 作者 (個人) |
| `owner` | 負責人 (team / person) |
| `related` | `[id1,id2,...]` 跨 block 關聯 |

### 媒體相關 (type:figure / chart / table / video)
| Key | 規則 |
|---|---|
| `alt` | 圖片 alt 文字 |
| `media` | `image` / `video` / `audio` / `svg` |
| `transcript` | 影片 / 音訊 transcript 檔案路徑 |
| `duration` | 影片 / 音訊長度 (`2m30s`) |
| `chart-type` | `vega-lite` / `plotly` / `chartjs` / `mermaid` / ... |
| `data-source` | CSV / JSON 資料檔路徑 |

### 表格增強 (type:table)
| Key | 規則 |
|---|---|
| `sortable` | `true` / `false` |
| `searchable` | `true` / `false` |
| `summary-row` | `sum` / `avg` / `count` / `none` |
| `pagination` | 數字 (per page) |

### KPI / Gauge / Targets (type:kpi / gauge / targets)
| Key | 規則 |
|---|---|
| `metric` | 指標名稱 |
| `value` | 當前值 |
| `target` | 目標值 |
| `delta` | 變動 (`+12%` / `-3` / `+1.2M`) |
| `unit` | 單位 (`%` / `USD` / `ms`) |
| `min` | gauge 下限 |
| `max` | gauge 上限 |
| `zones` | gauge 區段定義 (`[99.0:red,99.9:amber,99.95:green]`) |
| `period` | 時間範圍 (`2026-Q1`) |

### Variant (tabbed UI)
| Key | 規則 |
|---|---|
| `variant-group` | 群組 ID (siblings 共用) |
| `variant` | 該 sibling 的變體值 (`mac` / `linux` / 等) |

### Dialogue (type:dialogue / turn)
| Key | 規則 |
|---|---|
| `participants` | `[ann,bob]` |
| `speaker` | 該 turn 的發言者 |
| `time` | 時間戳 |

### Dashboard / Card
| Key | 規則 |
|---|---|
| `layout` | `grid` / `stack` |
| `columns` | `auto` / 數字 |
| `accent` | `info` / `warning` / `success` / `danger` |

## 4. Metadata 約束關係(必須一致)

下列是 hard implication,違反時 viewer 行為不可預期:

| 條件 | 必須伴隨 |
|---|---|
| `status:deprecated` | `superseded-by:<valid-id>` |
| `status:superseded` | `superseded-by:<valid-id>` |
| `type:history` 或內容性質為 archive | `visibility:collapsed` |
| `type:kpi` | `value:` 必填,且與 prose 段數字一致 |
| `type:gauge` | `value:` `min:` `max:` `zones:` 必填 |
| sibling 共用 `variant-group:` | 每個 sibling `variant:` 值不可重複 |
| `type:figure` / `chart` / `video` / `audio` | 必須有 prose companion paragraph |
| 表格 > 30 列 | 不可 inline,必須 `data-source:` |

## 5. 寫好 metadata 的最大化 AI/人類可讀性檢核

撰寫 metadata 時自問:

### AI 友善
1. **`summary:` 在嗎?**(如有需要)能讓另一個 AI 在不展開 body 的情況下,判斷這 block 與當前任務是否相關?
2. **`type:` 對嗎?**(對應的 closed vocabulary 值)能讓 retrieval 系統做 type-filter?
3. **`status:` 反映真實狀態?**(避免歷史內容被誤當現況)
4. **`updated:` 是新的?**(過時內容應降級或 archive)
5. **跨 block 關聯有用 `superseded-by:` / `related:` 標記?**(讓 AI 跟隨)

### 人類友善
1. **block id 看名字就猜得到內容?**
2. **`title:`(若有)或 H 標題在 viewer 一眼看得到?**
3. **`status:` 會被 viewer 渲染成 colored pill,讀者一秒判斷?**
4. **`updated:` 在標題列顯示?**(讀者知道資訊新舊)
5. **`tags:` 在頁尾或側欄顯示,可點擊過濾?**
6. **`audience:` 控制了該 block 是否要對特定身份隱藏?**

兩邊都 YES 才算合格 metadata。

## 6. 反模式 (anti-patterns)

| Anti-pattern | 為什麼錯 | 改成 |
|---|---|---|
| `type:section` `type:subsection` | 過度泛用,沒語義 | 用具體 type (`state` / `note` / `spec`) |
| `tags:[important,must-read,key]` | 主觀且重複 | 用 `priority:high` |
| `style:warning-banner` | metadata 描述了樣式 | 改成 `accent:warning` (還是行為宣告,viewer 決定渲染) |
| 同一 block 有 `status:active` 與 `status:deprecated` | 矛盾 | 拆成兩個 block,deprecated 那個 archive |
| `summary:` 寫了三段文字 | 不是 summary,是 body | summary 一句宣告;細節寫 body |
| metadata 數字 ≠ prose 數字 | AI 摘要會錯 | 兩邊必須一致;改一處就改兩處 |
| `tags:` 含中文混英文混縮寫 | 不可預測 | 統一用 kebab-case 英文,或全用中文 |
| `superseded-by:` 指向不存在的 id | 死連結 | 寫完整份再回頭驗證,或用工具檢查 |
