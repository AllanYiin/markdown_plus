# Q1 2026 Auth Service Status Report

Q1 Auth service 績效摘要、SLO 達成、風險與 Q2 計畫。

- **#exec-summary** `type:note` `priority:high` `updated:2026-05-13`
  Q1 整體 on-track,但 5/3 一次 14 分鐘 outage 拉低 SLA 到 99.92%(目標 99.95%)。
  Root cause 已 fix(Token Service memory leak),canary deployment 改善方案於 Q2 上線。

- **#exec-dashboard** `type:dashboard` `layout:grid` `period:2026-Q1`

  *Dashboard: Q1 重點 KPI*

  - **#sla-kpi** `type:kpi` `metric:API_SLA` `value:99.92` `unit:%` `target:99.95` `delta:-0.03` `status:behind`
    API SLA 99.92%,目標 99.95%,本季因 5/3 outage 扣分 0.03 個百分點。

  - **#latency-kpi** `type:kpi` `metric:p99_latency` `value:218` `unit:ms` `target:250` `delta:-12` `status:on-track`
    p99 latency 218ms,優於 250ms 目標,本季較上季降 12ms。

  - **#error-kpi** `type:kpi` `metric:error_rate` `value:0.38` `unit:%` `target:0.5` `delta:-0.07` `status:on-track`
    錯誤率 0.38%,優於 0.5% SLO。

  - **#mttr-kpi** `type:kpi` `metric:MTTR` `value:22` `unit:min` `target:30` `delta:-5` `status:on-track`
    MTTR 22 分鐘,優於 30 分鐘目標。

- **#sla-gauge** `type:gauge` `metric:API_SLA` `value:99.92` `unit:%` `min:99.0` `max:100` `target:99.95` `zones:[99.0:red,99.9:amber,99.95:green]`

  *Gauge: API SLA (目標 99.95%)*

  目前落在 amber 區間。距 green 區間還差 0.03 個百分點,Q2 需把 outage 數量歸零。

- **#q1-targets** `type:targets` `period:2026-Q1`

  *Targets: Q1 SLO 達成狀況*

  | 指標            | Target  | Actual  | Status            |
  |-----------------|---------|---------|-------------------|
  | API SLA         | 99.95%  | 99.92%  | `status:behind`   |
  | p99 latency     | <250ms  | 218ms   | `status:on-track` |
  | Error rate      | <0.5%   | 0.38%   | `status:on-track` |
  | MTTR            | <30m    | 22m     | `status:on-track` |

  4 項指標中 3 項 on-track,僅 SLA 落後。改善方向見 `#q2-plan`。

- **#q2-plan** `type:task` `status:open` `owner:platform-team`

  - **#action-canary** `type:task` `status:open` `owner:alice`
    Token Service canary deployment(10% → 30% → 100%)上線,目標 2026-06-30。

  - **#action-memory-alert** `type:task` `status:done` `owner:dave`
    Memory alert 已上線(6GB warning、7GB critical)。
