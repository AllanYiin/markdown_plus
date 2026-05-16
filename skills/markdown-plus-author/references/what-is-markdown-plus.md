# 什麼是 Markdown+,為什麼需要它

## 0. TL;DR 與實證數據

**Markdown+ 是純 Markdown + 三個習慣**(bullet-list block + 外部媒體路徑 + figure/table/chart 的 prose companion)+ 一份受控 metadata 字彙表。

**100 次 gpt-5.5 API call 實測(5 use cases × 5 docs × 4 formats)的 output token 成本**:

| 格式 | tokens 比 Markdown | 改寫時間比 Markdown |
|---|---|---|
| Markdown | 1.00× (baseline,12,428 tokens 均) | 1.00× (182s 均) |
| **Markdown+** | **1.46×** (18,102 均) | **0.75×** (137s 均,反而快) |
| Medium HTML | 1.70× (21,083 均) | 1.02× (187s 均) |
| Heavy HTML | **2.37×** (29,427 均) | 1.49× (272s 均) |

**結論**:文章「HTML 多耗 tokens 微乎其微」**經實證不成立**:Heavy HTML +137%,Medium HTML +70%。Markdown+ 是穩定中間選項,且改寫時間反而比生成原 Markdown 快(因為有原文當參考)。

每 use case 詳細數字:

| Use Case | Cases | Mean MD | Mean MD+ | Mean Medium HTML | Mean Heavy HTML | MD+/MD | Heavy/MD |
|---|---|---|---|---|---|---|---|
| API Reference | 5 | 12,060 | 17,439 | 19,823 | 28,419 | 1.45× | 2.36× |
| Meeting Notes / Decision Records | 5 | 11,667 | 16,680 | 20,412 | 29,937 | 1.43× | 2.57× |
| Research / Investigation Report | 5 | 11,494 | 16,468 | 21,441 | 25,145 | 1.43× | 2.19× |
| Technical Spec / PRD | 5 | 17,984 | 26,537 | 29,540 | 33,654 | 1.48× | 1.87× |
| Tutorial / How-to | 5 | 8,937 | 13,387 | 14,200 | 29,979 | 1.50× | 3.35× |
| **All (mean of means)** | 25 | **12,428** | **18,102** | **21,083** | **29,427** | **1.46×** | **2.37×** |

特別注意:**Tutorial 在 Heavy HTML 下達 3.35×**(步驟型內容轉互動 UI 需要大量 navbar / step navigator / 互動容器)。Markdown+ 在所有 use case 比例極穩(1.43×–1.50×),Heavy HTML 卻 1.87×–3.35× 大幅震盪。

---

## 1. 一句話定義

**Markdown+ = 純 Markdown + 三個習慣 + 一份受控字彙表。**
不是新格式,不是新 dialect,不是 markdown extension。是「用既有 markdown 語法養成可被機器穩定查詢、又能被人類舒服閱讀的撰寫習慣」。

## 2. 為什麼需要它

在 AI agent 大量參與文件生產的世界裡,一份文件同時面對兩種讀者:

| 讀者 | 期待 |
|---|---|
| AI agent (parser / retriever / reviewer) | 低冗餘、高語義密度、可局部讀取、可精準修改、穩定 ID |
| 人類 (作者 / 同事 / 客戶) | 視覺層級、目錄、摺疊、圖表、callout、互動 |

傳統做法走極端:
- 純 Markdown:對 AI 友善但人類閱讀體驗陽春
- HTML:對人類閱讀漂亮但 AI 讀起來充滿 tag 噪音、tokens 暴漲、難以局部修改
- HTML 內嵌 Markdown 或 Markdown 內嵌 HTML:兩邊都做不好,維護成本爆炸

Markdown+ 的立場是 **本體與投影分工**:
- **本體 (source)** 是給 AI 的工作介面:純 Markdown + 受控 metadata
- **投影 (view)** 是給人類的閱讀介面:由 viewer 把 source 渲染成有 nav、status pill、card、gauge 的 HTML

source 不負責長得漂亮,viewer 不負責保存語義。

## 3. 為什麼不直接用 `:::block` directive

很多 markdown-extension 走「自訂 fence directive」路線(例如 Pandoc fenced div 的 `:::block`)。Markdown+ **明確拒絕**這條路,因為:

1. `:::` 在純 markdown viewer 顯示為亂碼,破壞 graceful degradation
2. `:::` 內外層 close 配對有歧義,parser 不穩
3. 加 directive 等於發明新 dialect,既有工具鏈(GitHub、Obsidian、VS Code、IDE preview)都要寫專屬處理
4. AI 模型遇到陌生 fence 容易誤生成、誤閉合

Markdown+ 走的是 **Mermaid 路線**:像 Mermaid 在 GitHub render 成圖、在純文字 editor 看是合法 code fence 一樣,Markdown+ 在 GitHub 看是有結構的 bullet list、在專用 viewer 看是有互動的文件。**source 從頭到尾是合法 CommonMark,不需要任何 dialect 支援**。

## 4. 精神 (核心三習慣)

### 習慣 1:substantive section = bullet-list block

每個語義獨立的章節,寫成 bullet list item,開頭固定格式:

```markdown
- **#<id>** `type:<value>` [`<key>:<value>` ...]
  <body>
```

- `**#id**` 是 block 的錨點(像 hashtag,純 markdown 看是粗體)
- inline code `key:value` 是 metadata(純 markdown 看是 monospace badge)
- 縮排自然表達父子關係,無需顯式 fence

### 習慣 2:binary media 一律外部相對路徑

image / video / audio / svg / 大型 chart spec 都用 `./relative/path` 引用,**永不** inline、**永不** base64。理由:base64 是 LLM context 殺手,單張圖可吃掉幾萬 tokens 還毫無語義。

### 習慣 3:每個 figure / table / chart / KPI 必有 prose companion

不論 viewer 多漂亮,source 端的數字、圖、表都要伴隨一段文字描述。理由:讓 AI 不用 OCR、不用 render chart 也能用這個 block 回答問題;讓盲讀者、純文字環境、grep 使用者也能取得資訊。

## 5. 設計原則(規範與準則)

### Principle 1 — Graceful degradation
Source 必須是合法 CommonMark。在 vanilla markdown viewer 開啟,看到的應該是清楚的 bullet list + inline code + italic caption + 標準表格,**絕無**亂碼 / 未渲染的 fence / 殘留 directive。

### Principle 2 — Source 高語義密度,Viewer 高視覺密度
Source 加的每個 token 都應該對 AI 有用 (metadata、prose companion)。Visual richness 是 viewer 的責任,不是 source 的責任。Source 不要寫 CSS class、不要寫 inline style、不要寫 layout wrapper。

### Principle 3 — Closed metadata vocabulary
`type:` / `status:` / `trend:` / `visibility:` 是受控字彙表,viewer 才能穩定渲染。需要擴充時用 `x-` 前綴 (例如 `type:x-endpoint`),並要明定 fallback 投影規則。

### Principle 4 — 不寫死視覺
不要在 source 中寫死「Figure 1」「Table 2」這類編號 — 編號由 viewer 依 block manifest 順序自動產。也不要寫死顏色、字型、layout columns — 全交給 viewer。

### Principle 5 — Block 是文件操作的最小單位
read / query / modify / reorder 都以 block 為單位。每個 block 有穩定 id,reorder 不破壞引用;每個 block 可獨立摘要、獨立索引、獨立 archive。

### Principle 6 — Metadata 約束關係必須一致
某些 metadata key 之間有 implication:
- `status:deprecated` ⇒ 必須有 `superseded-by:<id>`
- `type:history` 或 archive 性質的 block ⇒ 必須 `visibility:collapsed`
- siblings 共用 `variant-group:` ⇒ 每個 `variant:` 值必須相異

違反這些 implication 等於語義腐爛,viewer 行為會混亂。

### Principle 7 — Prose 是 AI 的 alt text
每個含視覺資料的 block (圖、表、chart、KPI、gauge),source 端必須有一段散文描述「這個視覺呈現了什麼、結論是什麼」。alt 屬性不夠,因為 alt 只描述「圖中有什麼」,prose 還要解釋「為什麼重要」。

### Principle 8 — Large data 走 data-source,不要 inline
表格超過約 30 列、chart spec 超過約 80 行、SVG 任何尺寸 → 一律外部檔案。source 變成 thin pointer,實際資料給 viewer 載入。

## 6. 對應到傳統文件型態

Markdown+ 不是萬用格式,它最適合下列文件:

| 文件型態 | 為什麼 Markdown+ 加分 |
|---|---|
| Dev note / decision record / ADR | 現況 vs 歷史的時序語義,Markdown+ 用 `type:state` / `type:history` 表達自然 |
| 技術規格 / PRD | 結構化、可索引、可修訂、可 link |
| Research report / investigation | 證據鏈、cross-link、可摘要 |
| Status report / executive brief | KPI / gauge / dashboard 元件天然契合 |
| Runbook / playbook | step 序列、status 標記、variant (OS / region) |
| Interview transcript / Q&A | dialogue 模式 |

不適合:
- 投影片 / slides — 改用 pptx-maker
- 一次性短訊 / email — 直接寫 markdown 或 plain text
- 長篇散文 / essay / 文學作品 — 結構化會破壞文體
- 純參考表 / cheat sheet (沒有需要 block 化的章節) — 直接寫 markdown table

## 7. 與其他 markdown 流派的關係

| 流派 | 立場 |
|---|---|
| CommonMark | Markdown+ 的 **基底**,所有 source 都必須合法 CommonMark |
| GitHub Flavored Markdown (GFM) | **支援**。task list、表格、GFM alert (`> [!NOTE]`) 都允許使用 |
| Pandoc fenced div (`:::block`) | **拒絕**。違反 graceful degradation |
| MDX / JSX-in-md | **拒絕**。破壞 CommonMark 合法性 |
| YAML frontmatter | **允許但限用**。整份文件 metadata 可放 frontmatter,但 block 級 metadata 一律用 inline code |
| Mermaid / vega-lite / plantuml fence | **支援**。它們本身就 LLM-friendly,fence 包起來符合 graceful degradation |
| Inline HTML | **嚴格限制**。只允許 CommonMark 公認的 `<br>` `<hr>` `<sub>` `<sup>`,其他一律拒絕 |
| Inline base64 / data URI | **禁止**。是 hard lint error |
