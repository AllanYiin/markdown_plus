# Worked Examples

每組都是「左輸入 / 右 Markdown+」對照。Markdown+ 同時在純 markdown viewer 與專用 viewer 都可讀。

## Example 1:Plain Markdown → Markdown+ (dev note)

### Input
```markdown
## Current auth state
We use Auth v2. Refresh token managed by gateway.

## History
Auth v1 stored tokens in cookies. Deprecated 2026-02.

## Open issues
- Mobile clients still using legacy header `X-Auth-Token`
- Need migration plan by Q3
```

### Output
```markdown
# Auth Service Notes

涵蓋目前 auth 流程、歷史版本、未解問題。

- **#current-state** `type:state` `status:active` `updated:2026-05-13` `tags:[domain:auth,module:gateway]`
  We use Auth v2. Refresh token managed by gateway.

- **#auth-v1** `type:history` `status:deprecated` `superseded-by:current-state` `updated:2026-02-15` `visibility:collapsed` `tags:[domain:auth,archive]`
  Auth v1 stored tokens in cookies. Deprecated 2026-02.

- **#mobile-legacy-header** `type:issue` `status:open` `priority:high` `tags:[domain:auth,client:mobile]`
  Mobile clients still using legacy header `X-Auth-Token`. Migration plan needed by Q3.
```

## Example 2:HTML → Markdown+ (dashboard with KPI)

### Input
```html
<article>
  <h1>Q1 Executive Dashboard</h1>
  <div class="dashboard grid-4col">
    <div class="kpi-card status-behind">
      <div class="metric-name">MRR</div>
      <div class="metric-value">$1.2M</div>
      <div class="metric-target">Target $1.5M</div>
      <div class="metric-delta positive">+12%</div>
    </div>
    <div class="kpi-card status-on-track">
      <div class="metric-name">Churn</div>
      <div class="metric-value">4.2%</div>
      <div class="metric-target">Target &lt;5%</div>
      <div class="metric-delta negative">-0.8%</div>
    </div>
  </div>
  <aside class="warning">
    <h2>Risk Watch</h2>
    <p>NPS dropped 3 points; investigate before Q2 plan.</p>
  </aside>
</article>
```

### Output
```markdown
# Q1 Executive Dashboard

Q1 重點指標彙整與當期風險警示。

- **#exec-dashboard** `type:dashboard` `layout:grid` `columns:auto` `period:2026-Q1`

  *Dashboard: Q1 重點 KPI*

  - **#mrr-kpi** `type:kpi` `metric:MRR` `value:1.2M` `target:1.5M` `delta:+12%` `status:behind`
    MRR $1.2M,目標 $1.5M,Q1 達成 80%,較上季 +12%。

  - **#churn-kpi** `type:kpi` `metric:Churn` `value:4.2%` `target:5%` `delta:-0.8%` `status:on-track`
    Churn 4.2%,優於 5% 目標,較上季 -0.8 個百分點。

- **#nps-risk** `type:issue` `status:open` `priority:high` `tags:[domain:product]`
  NPS dropped 3 points; investigate before Q2 plan.
```

注意:HTML 的 `<aside class="warning">` 變成 `type:issue` + `priority:high`,prose 段保留原文重點。`<div class="kpi-card">` 變成 `type:kpi`,**且每張 KPI 都加了 prose companion**。

## Example 3:Tutorial 含 OS variants

### Input
```markdown
## Install
### macOS
brew install foo

### Linux
apt install foo

### Windows
scoop install foo
```

### Output
```markdown
# foo CLI 安裝

依作業系統選擇安裝方式。

- **#install-mac** `type:step` `variant-group:install` `variant:mac`
  *Listing: macOS 安裝指令*
  ` ` `bash
  brew install foo
  ` ` `
  macOS 透過 Homebrew 安裝。

- **#install-linux** `type:step` `variant-group:install` `variant:linux`
  *Listing: Linux 安裝指令*
  ` ` `bash
  apt install foo
  ` ` `
  Debian/Ubuntu 系列 Linux 透過 apt 安裝;其他發行版請查官方文件。

- **#install-windows** `type:step` `variant-group:install` `variant:windows`
  *Listing: Windows 安裝指令*
  ` ` `bash
  scoop install foo
  ` ` `
  Windows 透過 Scoop 安裝;若沒有 Scoop 請改用 Chocolatey。
```

純 markdown viewer:三個 sibling block 都看得到。
Markdown+ viewer:自動偵測 `variant-group:install` 聚合成三個 tab,預設展開使用者作業系統匹配的那個。

## Example 4:Decision Record (ADR 風格)

### Output
```markdown
# ADR-014: 將 monorepo 工具從 Lerna 換成 Turborepo

涵蓋背景、評估過的選項、決議與行動項。

- **#context** `type:state` `updated:2026-05-13` `tags:[domain:tooling,team:platform]`
  目前 monorepo 用 Lerna 6 管理 12 個 packages。CI 全量重建耗時 18 分鐘,
  developer 本地切換 branch 後 rebuild 平均 4 分鐘。痛點:沒有 incremental
  build cache、沒有 task graph 平行化。

- **#options** `type:spec`
  評估了三個候選方案。

  - **#option-turborepo** `type:spec` `tags:[tool:turborepo]`
    Turborepo 提供 task graph 平行化與 remote cache。維護方為 Vercel,
    與 Next.js 整合佳。學習曲線中等。

  - **#option-nx** `type:spec` `tags:[tool:nx]`
    Nx 功能最完整含 generators 與 plugin 生態。但 config 較重,
    從 Lerna 遷移幅度大。學習曲線陡。

  - **#option-stay-lerna** `type:spec` `tags:[tool:lerna]`
    保留 Lerna 7,新版加入 nx 整合可選用。但與獨立 Turborepo / Nx 相比仍欠 incremental。

- **#decision** `type:decision` `status:accepted` `updated:2026-05-13`
  採用 **Turborepo**。理由:incremental build 解決最大痛點、與既有 Next.js
  + pnpm 工作流匹配、學習曲線可接受。

- **#actions** `type:task` `status:open` `owner:platform-team`

  - **#action-poc** `type:task` `status:done` `owner:alice`
    完成 Turborepo POC 在 2 個 packages 上,build 時間從 4 分 → 45 秒。

  - **#action-rollout** `type:task` `status:open` `owner:bob`
    全 repo rollout,預計 2026-05-31 前完成。

  - **#action-ci-update** `type:task` `status:blocked` `owner:carol`
    CI pipeline 接入 remote cache,blocked on GitHub Actions IP allowlist。

- **#rejected-lerna-7** `type:history` `status:rejected` `visibility:collapsed`
  保留 Lerna 7 方案被駁回:即使加 nx 整合,基礎能力仍不如 dedicated 工具,
  維護心智成本不下降。
```

## Example 5:Research report 含 chart + table

### Output
```markdown
# 向量資料庫延遲與成本比較

比較三家向量資料庫在 1000 萬筆向量下的查詢延遲與營運成本。

- **#methodology** `type:spec` `updated:2026-05-13`
  測試資料集:10M × 768-dim float32 向量。Query workload:
  10k 隨機查詢,k=10。三家 DB 各部署在 m5.4xlarge × 3 節點。

- **#latency-results** `type:table` `sortable:true` `summary-row:none`

  *Table: p99 query latency (ms) by k value*

  | DB        | k=10 | k=50 | k=100 | k=500 |
  |-----------|------|------|-------|-------|
  | Pinecone  | 28   | 42   | 58    | 145   |
  | Weaviate  | 35   | 51   | 68    | 162   |
  | Qdrant    | 22   | 38   | 52    | 130   |

  Qdrant 在所有 k 值都最快;Pinecone 次之;Weaviate 最慢但仍可接受。
  k=500 時三家差距收斂到 ~25%。

- **#cost-chart** `type:chart` `chart-type:vega-lite` `data-source:./data/vector-db-cost.csv`

  *Chart: 月度營運成本(USD,1000 萬向量)*

  ![Cost comparison](./charts/vector-db-cost.vl.json)

  Pinecone 月成本最高($2,400),包含 managed service premium;
  Qdrant 自架最便宜($890)但需要運維 headcount;
  Weaviate 自架居中($1,150)。

- **#recommendation** `type:decision` `status:proposed` `updated:2026-05-13`
  建議在 staging 採用 **Qdrant** 自架(成本 + 延遲俱佳),production
  視 SLO 與 ops 能量決定;若 ops 量能受限再評估 Pinecone managed。

- **#followup-batch-test** `type:task` `status:open` `owner:data-platform`
  下一步補測 batch insert 延遲與索引重建時間,當前 benchmark 未涵蓋。
```

## Example 6:Interview transcript (dialogue)

### Output
```markdown
# User Interview — 訪談 Bob,2026-05-10

針對新版 API 痛點的 30 分鐘訪談。

- **#interview-2026-05-10** `type:dialogue` `participants:[ann,bob]` `source:interview-recording-2026-05-10`

  - **#turn-1** `type:turn` `speaker:ann` `time:14:02`
    > 你覺得新版 API 最大的痛點是什麼?

  - **#turn-2** `type:turn` `speaker:bob` `time:14:02`
    > 錯誤訊息太抽象。"Invalid request" 但不告訴我哪個欄位錯,
    > 而且 trace ID 沒回傳,沒辦法 escalate。

  - **#turn-3** `type:turn` `speaker:ann` `time:14:03`
    > 那 SDK 的部分呢?

  - **#turn-4** `type:turn` `speaker:bob` `time:14:04`
    > Python SDK 還行,但 TypeScript types 跟 OpenAPI spec 對不上,
    > 有時候會少欄位,得自己手動補。

- **#interview-takeaways** `type:note` `priority:high`
  兩個主要痛點:
  (1) 錯誤訊息缺乏可操作性 — 需要欄位粒度錯誤 + trace ID;
  (2) TypeScript SDK 與 OpenAPI spec 漂移 — 需要 codegen pipeline。
```

## Example 7:Gauge + Targets

### Output
```markdown
# Q1 SRE Scorecard

API SLA 與服務目標達成情況。

- **#sla-gauge** `type:gauge` `metric:API_SLA` `value:99.92` `unit:%` `min:99.0` `max:100` `target:99.95` `zones:[99.0:red,99.9:amber,99.95:green]` `period:2026-Q1`

  *Gauge: API SLA(目標 99.95%)*

  API SLA 99.92%,落在 amber 區間(99.0–99.95)。本季扣分主因為
  2026-05-03 那次 14 分鐘 outage(Gateway memory leak),
  詳見 incident report `#inc-2026-05-03`。

- **#q1-targets** `type:targets` `period:2026-Q1`

  *Targets: Q1 SLO 達成*

  | 指標            | Target  | Actual  | Status              |
  |-----------------|---------|---------|---------------------|
  | API SLA         | 99.95%  | 99.92%  | `status:behind`     |
  | p99 latency     | < 250ms | 218ms   | `status:on-track`   |
  | Error rate      | < 0.5%  | 0.38%   | `status:on-track`   |
  | MTTR            | < 30m   | 22m     | `status:on-track`   |

  4 個指標中 3 個 on-track,僅 SLA 落後。改善方向:
  (1) Gateway memory leak fix 已 merge;
  (2) 加上 canary deployment 降低未來 outage 影響面;
  (3) 把 SLA 計算口徑從 monthly 改為 rolling 30-day,降低單次事件影響。

- **#related-inc** `type:reference` `related:[sla-gauge]`
  Incident report:`./incidents/2026-05-03-gateway-outage.md`(14m outage)。
```

## Example 8:Bad / Good 對照

### Bad (反模式)
```markdown
- **#some-thing** `type:section` `priority:critical` `style:warning-banner`
  This is super important you must read this.

  Auth is bad. Fix it. ASAP.
```

問題:
1. `type:section` 沒語義 → 用 `type:issue`
2. `priority:critical` 過度誇張 → 多數情況 `priority:high` 就夠
3. `style:warning-banner` 是視覺指令 → 改成 `accent:warning` 由 viewer 決定
4. body 是情緒口語,沒有事實 → 改寫成可執行內容
5. 沒有 `updated:`、沒有 `owner:`、沒有 `tags:` → 補上

### Good (修正版)
```markdown
- **#auth-vuln-2026-05** `type:issue` `status:open` `priority:high` `owner:security-team` `updated:2026-05-13` `accent:warning` `tags:[domain:auth,severity:high]`
  Auth v2 refresh token 在 mobile client 上未驗證 audience claim,
  可被跨服務重放。CVE 編號申請中。修正 PR:`./prs/2347-auth-aud-fix.md`。
  建議 2026-05-20 前完成 hotfix 與 mobile force-upgrade。
```

修正點:
- type 從 `section` 改 `issue`
- 加 `status` `priority` `owner` `updated` `tags`
- 視覺 `style:warning-banner` → 行為 `accent:warning`
- body 從口語改成事實 + 動作項

## Example 9:整份 minimal but complete document

完整、可直接用、含絕大多數 block type 的範本。建議當作快速 reference。

```markdown
# Markdown+ 範本(完整骨架)

Markdown+ 文件結構與常用 block type 範例。

- **#intro** `type:note` `priority:normal`
  這份文件示範常用 block type。實際撰寫時可只用需要的種類。

- **#current-state** `type:state` `status:active` `updated:2026-05-13`
  描述系統當前狀態。

- **#decision-2026-05** `type:decision` `status:accepted` `updated:2026-05-13`
  本期關鍵決策。

- **#kpi-overview** `type:kpi` `metric:MRR` `value:1.2M` `target:1.5M` `delta:+12%`
  MRR $1.2M,Q1 達成 80%。

- **#open-issue-1** `type:issue` `status:open` `priority:high` `owner:alice`
  Issue 描述、影響、行動。

- **#step-do-x** `type:task` `status:open` `owner:bob`
  Task 行動項。

- **#history-v1** `type:history` `status:deprecated` `superseded-by:current-state` `visibility:collapsed`
  歷史紀錄。

- **#references** `type:reference` `related:[decision-2026-05]`
  - Spec: `./specs/auth-v2.md`
  - PR: `./prs/2347-auth-aud-fix.md`
```
