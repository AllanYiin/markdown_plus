# 品質檢查清單

`markdown-plus-author` 的 readiness gate。skill 改版時填上稽核結果;每次產出 Markdown+ 文件時跑「per-document checks」。

## Readiness Gate(最終關卡)

- **Audit date**: 2026-05-13
- **Compliance level**: Phase 4 — compatibility/trust/install audit completed
- **Overall status**: `PASS`(見下方 audits 結果)
- **Blocking issues**: 無
- **Automated checks**:
  - [x] `python <skill-creator-advanced>/scripts/format_check.py markdown-plus-author` — see audit log section
  - [x] `python <skill-creator-advanced>/scripts/quick_validate.py markdown-plus-author`
  - [x] `python <skill-creator-advanced>/scripts/audit_skill_references.py markdown-plus-author`
  - [x] `python <skill-creator-advanced>/scripts/audit_unreferenced_files.py markdown-plus-author`

## 格式檢查(Skill 改版時跑)

- [x] Skill folder 名稱:`markdown-plus-author`(kebab-case)
- [x] `SKILL.md` 存在,UTF-8
- [x] YAML frontmatter 含 `name` + `description`
- [x] `description` 含真實 trigger phrases(dev note / decision record / research report / tech spec / status report / ADR / runbook / rewrite Markdown / rewrite HTML)
- [x] `description` 同時寫「何時用、何時不用、成功輸出長什麼樣」
- [x] 沒有 README.md 在 skill folder 內(讓 skill-creator-advanced rule 11 通過)
- [x] 所有 `references/` 引用路徑都存在(7 個 references,1 個新增的 `code-fence-preservation.md`)
- [x] 沒有 orphan 檔案

## 需求 / 規範檢查

- [x] 只負責一件主要工作:產出或改寫 Markdown+ 文件
- [x] `<decision_boundary>` 明寫 use / do-not-use / successful output
- [x] `<workflow>` 每步有 Input / Action / Output / Validation
- [x] `<output_contract>` 列出可機械驗證的 PASS 條件(14 條,含新加的 verbatim preservation)
- [x] `<default_follow_through_policy>` 明寫 direct / ask-first / stop-report 三類動作
- [x] Hard requirement 用「必須」「不得」「一律」「禁止」表達(不寫成軟性「若」)
- [x] 內含 worked example(SKILL.md 末尾的 plain markdown → markdown+ + `references/worked-examples.md` 9 組)
- [x] **新增**:`<empirical_evidence>` 區塊提供 100-call benchmark 數據,可用於說服 skeptical reader

## 文件輸出品質檢查(per-document,每次產出文件時跑)

> SKILL.md `<workflow>` Step 7 必須跑完下列所有項目。

- [ ] 每個 block 都有 `**#<id>**` 與 `type:` metadata
- [ ] 所有 ID 是 kebab-case 且文件內唯一
- [ ] 沒有 `:::` fence
- [ ] 沒有除 `<br>` `<hr>` `<sub>` `<sup>` 之外的 raw HTML
- [ ] 沒有 `data:` URI / `base64,` / inline SVG
- [ ] 每個 `figure` / `chart` / `video` / `audio` / `table` / `kpi` / `gauge` 都有 prose companion paragraph
- [ ] 表格 > 30 列 → 使用 `data-source:./data/<name>.csv`
- [ ] Caption 沒寫死編號(`*Figure: ...*` 而非 `*Figure 1: ...*`)
- [ ] `status:deprecated` block 都有有效 `superseded-by:`
- [ ] `type:history` 或 archive block 都有 `visibility:collapsed`
- [ ] Sibling 共用 `variant-group:` 時每個 `variant:` 值不同
- [ ] `type:kpi` block 的 `value:` 與 prose 數字一致
- [ ] **新增**:Code fence、ASCII tree、aligned art 在原文中存在的話,輸出中**逐字保留**(byte-for-byte 含空白與換行;不可拍扁成段落)
- [ ] 在 vanilla CommonMark viewer 開啟,看到的是 bullet list + inline code + italic caption + 標準表格 + fenced code

## 常見錯誤檢查

- [ ] 沒有把 source 當 view 寫(沒在 source 加 nav / 卡片 / 互動 JS)
- [ ] 沒有把 view 當 source 寫(沒用 inline base64 把圖塞進 source)
- [ ] 沒有把 `type:` 開放成自由文字(closed vocabulary or `x-` prefix)
- [ ] 沒有把 hardcoded "Figure 1:" 等留在 caption
- [ ] 沒有把 deprecated 內容靜默刪除(必須 archive 並標 `superseded-by:`)
- [ ] 沒有把單一 block body 寫超長散文(>30 行考慮拆 sub-block)
- [ ] **新增**:沒有把 ASCII tree / aligned art 拍扁成 paragraph

## Audit log

### 2026-05-13 audit(本輪)

執行的 audit scripts 結果見下方 [Phase 4 audit results](#phase-4-audit-results)。

### Phase 4 audit results(2026-05-13)

```
===== format_check =====
[WARN] Description may be missing explicit trigger language.
Summary: 0 error(s), 1 warning(s).

Note: This warning is a false positive due to a regex escape bug in
format_check.py (TRIGGER_HINT_PATTERNS uses `r"\\bUse when\\b"` which
compiles to literal `\b...\b` instead of word-boundary `\b...\b`).
Our description does contain "Use when the user asks..." — manually verified.

===== quick_validate =====
Skill is valid!

===== audit_skill_references =====
Skill reference audit passed: 0 issues across 8 source file(s)

===== audit_unreferenced_files =====
Unreferenced file audit passed: 0 issues across 8 source file(s), 9 referenced file(s)

===== check_skill_name_surface =====
Name surface audit passed: 0 blocking issues

===== audit_skill_overlap =====
[markdown-plus-author] hit@1=0.0159 hit@3=0.0344
  - neighbor:spec-organizer score=0.0159 shared_triggers=-
  - neighbor:remotion-best-practices score=0.0104 shared_triggers=-
  - neighbor:technical-documentation-writer score=0.0081 shared_triggers=-

Very low overlap with all other skills; no shared triggers detected.
Description is distinctive enough to avoid routing fights with neighbors.
```

**Conclusion**: PASS. The single warning is a known tool false positive (not a content defect).

## Skill structure pattern

- Archetype: `executor` + `utility`
- Primary structure pattern: **Pipeline**(7 steps: detect → manifest → typing → write → caption+prose → enhance → validate)
- Embedded sub-patterns: `Generator`(strict output contract)、`Tool Wrapper`(教授 Markdown+ 慣例)

## Hand-off

- **Upstream**(常常導向本 skill):`markdown-anything`(把任意檔轉成 markdown 之後常接著要轉 Markdown+)、`technical-documentation-writer`(寫完 README/runbook 後)
- **Downstream**(本 skill 結束後可能跳出):`longform-writing-process`(若文件性質偏散文不適合 block 化)、`spec-organizer`(產品/系統 spec 整理)
- **Neighboring(易混淆)**:`mermaid-diagram`(只需要圖,不需要 block)、`markdown-anything`(只要把外部資料轉成 markdown,不需要 Markdown+ 化)
