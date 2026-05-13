# Code Fence & ASCII Art 逐字保留(Verbatim Preservation)

> 寫進 SKILL.md `<output_contract>` 的硬規則 — 改寫 Markdown / HTML → Markdown+ 時,某些內容必須**逐字保留**,不可改寫成散文、不可合併成一行、不可"美化"對齊。

## 1. 為什麼這條規則必要

實測案例:LLM 在改寫含「目錄樹」的 markdown 時,常見三種錯誤模式:

1. **拍扁成段落**:把多行樹合併成一句散文 `hippoium/├── README.md├── pyproject.toml...`,完全失去結構
2. **拆掉 fence**:把 ``` ``` 標記去掉,內容直接散落在 block body,viewer 把它當 paragraph,空白與換行被吃光
3. **"美化"對齊**:LLM 自作主張調整空白讓樹"更整齊",反而破壞原有對齊規則

任一情況下,使用者看到的成品都是壞掉的。原文資訊永久遺失(從輸出反推回原始對齊幾乎不可能)。

## 2. 必須逐字保留的內容類型

下列任一形式出現於原文時,在 Markdown+ 輸出**必須**:
- 用 ` ``` ` 或 ` ~~~ ` fence 包起來
- 內容 1:1 byte-for-byte 複製,包含每個空白、tab、換行
- fence 不可省、language 標籤不可改

### 2a. Code fence
原文有 ```` ``` ```` 或 `~~~` 開頭的 fenced code → 整段保留(fence 標記 + 內容 + 收尾 fence)

### 2b. ASCII tree / 目錄結構
含下列任一字元的多行內容:
- `│` (U+2502, BOX DRAWINGS LIGHT VERTICAL)
- `├` (U+251C, BOX DRAWINGS LIGHT VERTICAL AND RIGHT)
- `└` (U+2514, BOX DRAWINGS LIGHT UP AND RIGHT)
- `─` (U+2500, BOX DRAWINGS LIGHT HORIZONTAL)
- `┌` `┐` `┘` `┤` `┬` `┴` `┼` 或其他 U+2500–U+257F 範圍
- 或常見 ASCII tree 替代:`|` `+` `-`(配 nested 空白縮排)

### 2c. ASCII art
任何依賴等寬字體 + 對齊空白才有意義的多行內容(banner、流程示意、表格仿排)。

### 2d. 對齊資料表
固定欄寬靠空白對齊的純文字「表格」(不是 markdown table)。

### 2e. DSL fence
`mermaid` / `vega-lite` / `plotly` / `plantuml` 等已經是合法 markdown 慣例的 DSL fence,內容是該語言原文 → 整段保留。

## 3. 對應的 Markdown+ block 標註

當你把這類內容放進 Markdown+ block 時,建議為該 block 加註語意:

```markdown
- **#dir-structure** `type:diagram` `diagram-type:ascii-tree`

  *Figure: Hippoium 專案目錄結構*

  ` ` `
  hippoium/
  ├── README.md
  ├── pyproject.toml
  └── hippoium/
      ├── __init__.py
      └── ports/
  ` ` `

  Hippoium 採 Port/Protocol 優先設計,所有對外接口統一從 `ports/` 匯出。
```

`diagram-type:` 推薦值:`mermaid` / `ascii-tree` / `ascii-flow` / `vega-lite` / `plotly` / `chartjs` / `plantuml`。Viewer 可依此切換渲染策略。

## 4. 錯誤範例對照(✗ 不可這樣做)

### 錯誤 1:拍扁成段落
```markdown
- **#dir-structure** `type:figure`
  hippoium/├── README.md├── pyproject.toml├── hippoium/| | __init__.py# Port 層接口
```
**問題**:multiline 樹被合併成一句散文,空白被壓縮,box-drawing 字元跟內容黏在一起。讀者完全看不出層級。

### 錯誤 2:fence 被拆掉
```markdown
- **#dir-structure** `type:figure`
  hippoium/
  ├── README.md
  └── hippoium/
      ├── __init__.py
```
**問題**:沒有 ``` fence。`renderBody` 會把這些當 paragraph 處理,行間靠 markdown 段落規則合併,輸出依然壞掉。

### 錯誤 3:換成 markdown table
```markdown
- **#dir-structure** `type:table`
  | Level | Path |
  |-------|------|
  | 0 | hippoium/ |
  | 1 | README.md |
```
**問題**:把樹強塞進 table 格式,丟失視覺層級訊號,還增加了 LLM 沒有的事實(Level 欄位)。原作者意圖被改寫。

## 5. 正確範例(✓ 應該這樣做)

### Mermaid 序列圖
````markdown
- **#refresh-flow** `type:diagram` `diagram-type:mermaid`

  *Figure: Token refresh 流程*

  ```mermaid
  sequenceDiagram
      participant C as Client
      participant G as Gateway
      C->>G: request
      G-->>C: token
  ```

  refresh 流程對 client 透明,gateway 自動換 token。
````

### ASCII 目錄樹
````markdown
- **#project-layout** `type:diagram` `diagram-type:ascii-tree`

  *Figure: 專案目錄結構*

  ```
  myproject/
  ├── README.md
  ├── pyproject.toml
  └── src/
      ├── __init__.py
      └── core/
          ├── parser.py
          └── renderer.py
  ```

  src 下分 core 與後續會加的 plugins/ 目錄;每層維持「一個目錄一個職責」。
````

### Vega-Lite chart spec
````markdown
- **#q1-revenue-chart** `type:chart` `chart-type:vega-lite`

  *Chart: Q1 月度營收(USD)*

  ```vega-lite
  {
    "mark": "bar",
    "encoding": {
      "x": {"field": "month", "type": "ordinal"},
      "y": {"field": "revenue", "type": "quantitative"}
    }
  }
  ```

  3 月較 1 月成長 47%,主要驅動是 enterprise 新簽 23 筆。
````

## 6. 改寫器 prompt 應該包含的紅線

當你撰寫或調整 `markdown → markdown+` / `html → markdown+` 改寫器的 LLM prompt 時,**必須**包含下列其中一段(可從本檔複製):

> 【絕對不可改動的內容 — verbatim preservation】
> 原文中下列任一形式的內容,在 Markdown+ 輸出中必須**逐字保留**、**不可改寫成散文、不可合併成一行**:
> 1. Code fence (``` … ``` 或 ~~~ … ~~~):fence 標記、language 標籤、內容每一行、每個空白與換行,全部 1:1 複製
> 2. ASCII 樹狀結構 / 目錄結構(含 `│ ├ └ ─` 等 box-drawing 字元):一律放在一個 ``` fence 內;每一行獨立、每個對齊空白完整保留
> 3. ASCII art / 對齊表格 / 預先排版的文字:同上,放在 fence 內保留
> 4. Mermaid / vega-lite / plotly 等 DSL fence:fence 與內容逐字保留,只能在 metadata 加 `chart-type:` / `diagram-type:` 註明類型

## 7. Viewer 端的救援機制(防線 #2)

即使 prompt 規則被違反、source 已含「壞掉」的拍扁內容,渲染端可加偵測救援(`markdown-plus-ecosystem` 的 `mdp-viewer.mjs` 已實作):

```js
function looksLikePreformatted(lines) {
  if (lines.length < 2) return false;
  const boxRe = /[─-╿]/;
  const treePrefixRe = /^\s*(?:[│|]\s|[├└]──|[├└][─—\-])/;
  let boxHits = 0, treeHits = 0;
  for (const l of lines) {
    if (boxRe.test(l)) boxHits++;
    if (treePrefixRe.test(l)) treeHits++;
  }
  return boxHits >= 2
      || treeHits >= 2
      || (lines.length >= 3 && lines.every(l => /^[ \t]{2,}/.test(l)));
}
```

偵測命中時改用 `<pre>` 渲染,保留換行。**但這是救援機制,不是寬容理由**。改寫器仍應在 source 端就保留 fence;救援只防止已壞掉的內容看起來更糟。

## 8. 驗證步驟

跑 `markdown_plus_validator` 時加上下列檢查:
1. 文件中所有 `mermaid` / `vega-lite` / `plotly` fence 都還存在
2. block body 內若含 box-drawing 字元(`[─-╿]` 範圍),周圍必須有 ``` fence
3. 原 markdown 的 fence 數量 ≤ Markdown+ 輸出的 fence 數量(允許 viewer-friendly 註解新增 fence,不允許 fence 被吃掉)

第 2 條尤其關鍵 — 它能抓出「LLM 把樹拆成 paragraph」的失敗模式。
