# CHANGELOG

## 2026-05-13 — Website redesign (Stage 0 → 4)

### Stage 0: Design tokens
- `website/assets/site.css` 全面重寫,引入 design tokens(色彩、字級、間距、圓角、陰影、motion)
- 新增 `website/assets/playground.css`,專責 playground 的 IDE-style 元件
- 主色定為 indigo-700 `#4338ca`(高彩度深色),作為 nav 底色配白字
- 次色 cyan-600 `#0891b2` 給「+」與程式碼強調
- 全站淺色模式;程式碼塊在淺色下仍用深底反白以保可讀性
- 字型用 Inter + JetBrains Mono(系統字 stack 退路)

### Stage 1: Marketing 三頁
- `index.html` 重設 hero、gradient title、按鈕雙級系統、3-up pillar cards
- `syntax.html` 表格改 striped + hover、status 與 metadata 用 inline pill
- `tutorial.html` 步驟編號圓形 accent badge(`.tutorial-step`)、底部加 CTA

### Stage 2: Playground IDE-style
- 重做 `playground.html`,結構分:nav → sub-header(segmented tabs + 範例切換 + 全域 status)→ split pane(編輯器 / 預覽)→ 底部 issue drawer
- 編輯器面板有 file-tab chrome(accent dot + 檔名)
- 預覽面板有 browser-chrome(三圓點 + URL bar)
- Issue drawer 依錯誤狀態自動展開/收合
- Rewriter tab 為左輸入 / 中箭頭 / 右輸出三欄,下方 control bar
- 加入 localStorage 自動保存編輯內容(`mdp:playground:source`)與 tab 選擇

### Stage 3: Smoke tests
- 全部 6 個檔案靜態檢查 PASS(無遺漏色票、無斷連 asset)
- Playground 所有 cross-folder 路徑(`../samples/`、`../validator/`、`../viewer/`)解析成功

### Stage 4: 文件
- 新增 `README.md`(根目錄)
- 新增本 `CHANGELOG.md`

### Acceptance(checklist)
- [x] 全站淺色模式
- [x] Nav 用高彩度深色底 + 白字
- [x] 各頁套用統一 design tokens
- [x] Playground 預覽面板視覺明顯「不是 editor」
- [x] Tab switcher 為 segmented control 樣式
- [x] Status pill 三狀態 (PASS / WARN / FAIL) 顏色明確
- [x] Issue drawer 依 state 自動展開
- [x] localStorage 自動保存與恢復
- [x] 所有 cross-folder 路徑解析成功
- [x] 無新增第三方 JS 依賴

## 2026-05-12 — Initial ecosystem

- 建立 validator(Python + ESM)、viewer(Python + ESM)、rewriter(Python + Node)
- 建立 kitchen-sink 範例(33 blocks 涵蓋所有 type)
- 初版四頁靜態網站(深藍/灰色調,使用者回饋「醜到爆」)
