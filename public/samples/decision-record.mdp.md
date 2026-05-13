# ADR-014: 將 monorepo 工具從 Lerna 換成 Turborepo

涵蓋決策背景、替代方案、決議與行動項目。

- **#context** `type:state` `status:active` `updated:2026-05-13` `tags:[domain:tooling,team:platform]`
  目前 monorepo 用 Lerna 6 管理 12 個 packages。CI 全量重建耗時 18 分鐘,
  developer 本地切 branch 後 rebuild 平均 4 分鐘。痛點:沒有 incremental
  build cache、沒有 task graph 平行化。

- **#options** `type:spec`
  評估三個候選方案。

  - **#option-turborepo** `type:spec` `tags:[tool:turborepo]`
    Turborepo 提供 task graph 平行化與 remote cache。維護方為 Vercel,
    與 Next.js 整合佳。學習曲線中等。

  - **#option-nx** `type:spec` `tags:[tool:nx]`
    Nx 功能最完整含 generators 與 plugin 生態。但 config 較重,
    從 Lerna 遷移幅度大,團隊有人不熟。

  - **#option-stay-lerna** `type:spec` `tags:[tool:lerna]`
    保留 Lerna 7,新版加 nx 整合可選用。但 vs 獨立 Turborepo / Nx 仍欠 incremental build。

- **#decision** `type:decision` `status:accepted` `updated:2026-05-13` `owner:platform-team`
  採用 **Turborepo**。理由:incremental build 解決最大痛點、與既有 Next.js
  + pnpm 工作流匹配、學習曲線可接受。

- **#actions** `type:task` `owner:platform-team`

  - **#action-poc** `type:task` `status:done` `owner:alice`
    完成 Turborepo POC 在 2 個 packages 上,build 時間從 4 分 → 45 秒。

  - **#action-rollout** `type:task` `status:open` `owner:bob` `valid-until:2026-05-31`
    全 repo rollout,目標 2026-05-31 前完成。

  - **#action-ci-update** `type:task` `status:blocked` `owner:carol`
    CI pipeline 接入 remote cache,blocked on GitHub Actions IP allowlist。

- **#rejected-lerna-7** `type:history` `status:rejected` `superseded-by:decision` `visibility:collapsed`
  保留 Lerna 7 方案被駁回:即使加 nx 整合,基礎能力仍不如 dedicated 工具,
  維護心智成本不下降。
