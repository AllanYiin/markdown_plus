# Q1 2026 Auth Service Review

涵蓋現況、決策、KPI、issue、歷史與後續行動。本文件作為 Markdown+ 視覺元素的展示樣本。

- **#intro** `type:note` `priority:normal` `updated:2026-05-13`
  本檔示範 Markdown+ 在實際 service review 場景下的呈現方式,包含 KPI、gauge、表格、對話、變體、Mermaid、callout 等元素。

- **#exec-dashboard** `type:dashboard` `layout:grid` `period:2026-Q1`

  *Dashboard: Q1 Auth Service 重點指標*

  - **#sla-kpi** `type:kpi` `metric:API_SLA` `value:99.92` `unit:%` `target:99.95` `delta:-0.03` `status:behind`
    API SLA 99.92%,目標 99.95%,本季因 5/3 outage 扣分 0.03 個百分點。

  - **#latency-kpi** `type:kpi` `metric:p99_latency` `value:218` `unit:ms` `target:250` `delta:-12` `status:on-track`
    p99 latency 218ms,優於 250ms 目標,本季較上季降 12ms。

  - **#error-kpi** `type:kpi` `metric:error_rate` `value:0.38` `unit:%` `target:0.5` `delta:-0.07` `status:on-track`
    錯誤率 0.38%,優於 0.5% SLO。

  - **#mttr-kpi** `type:kpi` `metric:MTTR` `value:22` `unit:min` `target:30` `delta:-5` `status:on-track`
    MTTR 22 分鐘,優於 30 分鐘目標。

- **#sla-gauge** `type:gauge` `metric:API_SLA` `value:99.92` `unit:%` `min:99.0` `max:100` `target:99.95` `zones:[99.0:red,99.9:amber,99.95:green]`

  *Gauge: API SLA(目標 99.95%)*

  目前落在 amber 區間(99.9–99.95)。距 green 區間還差 0.03 個百分點,
  Q2 需把 5/3 那類 14 分鐘 outage 的數量歸零才能回到 green。

- **#q1-targets** `type:targets` `period:2026-Q1`

  *Targets: Q1 SLO 達成狀況*

  | 指標            | Target  | Actual  | Status            | Trend         |
  |-----------------|---------|---------|-------------------|---------------|
  | API SLA         | 99.95%  | 99.92%  | `status:behind`   | `trend:flat`  |
  | p99 latency     | <250ms  | 218ms   | `status:on-track` | `trend:down`  |
  | Error rate      | <0.5%   | 0.38%   | `status:on-track` | `trend:down`  |
  | MTTR            | <30m    | 22m     | `status:on-track` | `trend:down2` |

  4 項指標中 3 項 on-track,僅 SLA 落後。改善方向見 `#actions`。

- **#current-state** `type:state` `status:active` `updated:2026-05-13` `tags:[domain:auth,module:gateway]`
  目前 Auth v2 在 production 運作,refresh token 由 gateway 統一處理,
  三種 client(browser / mobile / server-to-server)各走不同 token 路徑。

- **#arch-diagram** `type:figure` `media:image` `alt:auth-three-tier-architecture`

  *Figure: Auth Service 三層架構*

  ![Auth flow architecture](./diagrams/auth-arch.png)

  圖中三層:Gateway(rate limit + auth)、Token Service(簽發/驗證)、Identity DB
  (使用者主檔)。Browser 走 httpOnly cookie、mobile 走 signed JWT、
  server-to-server 走 mTLS。

- **#refresh-flow** `type:diagram` `diagram-type:mermaid`

  *Figure: Token refresh 流程*

  ```mermaid
  sequenceDiagram
      participant C as Client
      participant G as Gateway
      participant T as Token Service
      C->>G: request with expired access token
      G->>T: validate refresh token
      T-->>G: new access token (15m TTL)
      G-->>C: 200 + new access token
  ```

  refresh 流程從 client 看是透明的,gateway 自動換 token,client 只感知重試一次。

> [!IMPORTANT]
> 5/3 那次 outage 與 token service memory leak 有關,詳見 `#inc-2026-05-03`,
> hotfix PR 已 merge 至 main,canary 部署中。

- **#decision-canary** `type:decision` `status:accepted` `updated:2026-05-13` `owner:platform-team` `tags:[domain:auth,strategy:deployment]`
  自 2026-Q2 起 Token Service 採 **canary deployment** 策略,
  10% 流量灰度 → 30% → 100%。理由:5/3 outage 顯示全量部署風險過高,
  且 token 邏輯異動偵測延遲可達 2 分鐘。

- **#inc-2026-05-03** `type:record` `status:active` `priority:high` `tags:[domain:auth,incident:outage]` `updated:2026-05-03`

  *Record: 2026-05-03 Token Service Outage*

  | 時間 (UTC) | 事件                                |
  |------------|-------------------------------------|
  | 03:14      | Token Service memory 突破 7.5GB     |
  | 03:16      | p99 latency 飆至 2.4s,oncall paged  |
  | 03:18      | Auto-restart 觸發,服務恢復          |
  | 03:28      | 全面恢復,後續監控 4 hr 無復發       |

  影響:14 分鐘 partial outage,約 8% 請求失敗。根因:JWT cache 未設上限,
  累積後 OOM。修正:設 LRU cache size = 100k、加 memory alert 在 6GB。

- **#install-steps** `type:spec`

  client SDK 安裝方式,依語言環境選擇。

  - **#install-py** `type:step` `variant-group:install` `variant:python`

    *Listing: Python SDK 安裝*

    ```bash
    pip install auth-sdk
    ```

    Python 3.10+ 透過 pip 安裝,自動帶 `httpx` 與 `pyjwt` 依賴。

  - **#install-js** `type:step` `variant-group:install` `variant:javascript`

    *Listing: JavaScript SDK 安裝*

    ```bash
    npm install @company/auth-sdk
    ```

    支援 Node 18+ 與現代瀏覽器(透過 esm build)。

  - **#install-go** `type:step` `variant-group:install` `variant:go`

    *Listing: Go SDK 安裝*

    ```bash
    go get github.com/company/auth-sdk-go
    ```

    需 Go 1.21+,使用 generics 簡化 token type 推導。

- **#interview-mobile-team** `type:dialogue` `participants:[ann,bob]` `source:interview-2026-05-08`

  訪談 Mobile team Bob 關於 Auth v2 整合痛點。

  - **#turn-1** `type:turn` `speaker:ann` `time:14:02`
    > Mobile 整合 Auth v2 最大的痛點是什麼?

  - **#turn-2** `type:turn` `speaker:bob` `time:14:02`
    > 錯誤訊息太抽象。"Invalid request" 但不告訴我是哪個欄位,
    > trace ID 也沒回傳,沒辦法 escalate。

  - **#turn-3** `type:turn` `speaker:ann` `time:14:04`
    > SDK 那邊呢?

  - **#turn-4** `type:turn` `speaker:bob` `time:14:05`
    > TypeScript types 跟 OpenAPI spec 對不上,有時候少欄位,
    > 得自己手動補。希望有 codegen pipeline。

- **#issue-error-msg** `type:issue` `status:open` `priority:high` `owner:auth-team` `accent:warning` `tags:[domain:auth,client:all]`
  錯誤訊息缺乏可操作性(來源 `#interview-mobile-team`):
  (1) 無欄位粒度錯誤碼;(2) 無 trace ID;(3) 文件未列舉錯誤型態。
  影響三類 client。Target fix:Q2 W4。

- **#issue-sdk-drift** `type:issue` `status:open` `priority:normal` `owner:dx-team` `accent:warning`
  TypeScript SDK 與 OpenAPI spec 漂移。需要建立 codegen pipeline 並
  在 CI 加 schema diff gate。

- **#actions** `type:task` `owner:platform-team`

  Q2 行動項目。

  - **#action-canary** `type:task` `status:open` `owner:alice` `valid-until:2026-06-30`
    完成 Token Service canary deployment 上線,目標 2026-06-30。

  - **#action-fix-errors** `type:task` `status:open` `owner:bob` `valid-until:2026-06-15`
    重構錯誤回應:加 field-level error code + trace_id,文件補錯誤目錄。

  - **#action-codegen** `type:task` `status:blocked` `owner:carol`
    建立 TypeScript SDK 自動 codegen pipeline。Blocked on OpenAPI spec
    完整性審查(Spec team 處理中)。

  - **#action-monitoring** `type:task` `status:done` `owner:dave`
    Token Service memory alert 已上線(6GB warning、7GB critical)。

- **#related-docs** `type:reference` `related:[decision-canary,inc-2026-05-03]`

  相關文件:
  - Token Service spec: `./specs/token-service-v2.md`
  - Incident 2026-05-03 full report: `./incidents/2026-05-03-token-oom.md`
  - Auth v2 migration runbook: `./runbooks/auth-v2-migration.md`

- **#auth-v1-history** `type:history` `status:deprecated` `superseded-by:current-state` `updated:2026-02-15` `visibility:collapsed` `tags:[domain:auth,archive]`

  Auth v1 歷史記錄。

  - **#auth-v1-design** `type:history` `status:deprecated` `superseded-by:current-state` `visibility:collapsed`
    Auth v1 把 access token 直接放在 cookie(無 httpOnly flag),
    refresh 邏輯由各 service 各自實作,缺乏統一 rotation 策略。
    2026-02-15 棄用,所有流量遷移至 Auth v2。

  - **#auth-v1-known-issues** `type:history` `status:deprecated` `superseded-by:current-state` `visibility:collapsed`
    已知問題(已隨 v2 解決):
    (1) Token 不 rotate → 長期暴露風險;
    (2) Cross-service refresh 不一致;
    (3) Mobile 無 secure storage。
