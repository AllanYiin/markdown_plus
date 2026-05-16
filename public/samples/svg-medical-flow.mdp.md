# 說服醫生流程 — Markdown+ SVG fence 示範

這份樣本用一張 12 KB 的醫藥行銷說服流程 SVG,展示 Markdown+ viewer 對中型 inline SVG 的渲染與 graph / code 切換能力。

- **#flow-overview** `type:note` `updated:2026-05-16`

  本流程從「客觀證據」推進到「合規溝通」再到「簡報」,涵蓋六個核心階段。
  完整視覺架構見下方 `#persuasion-flow-svg` block。

- **#persuasion-flow-svg** `type:figure` `media:svg` `alt:六階段說服醫生流程架構`

  *Figure: 說服醫生的整個流程架構(六階段 + 驗證回圈)*

  ```svg
  <svg width="1600" height="900" viewBox="0 0 1600 900" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="說服醫生的整個流程架構">
    <defs>
      <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#F7FAFF"></stop>
        <stop offset="100%" stop-color="#EEF4FF"></stop>
      </linearGradient>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%">
        <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#1F3B5B" flood-opacity="0.10"></feDropShadow>
      </filter>
      <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
        <path d="M0,0 L12,6 L0,12 Z" fill="#5B7CF0"></path>
      </marker>
      <style>
        .title { font: 700 34px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #183153; }
        .subtitle { font: 400 16px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #5C708A; }
        .chipText { font: 600 14px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #25476A; }
        .cardTitle { font: 700 22px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #FFFFFF; }
        .cardBody { font: 400 15px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #26435F; }
        .outputLabel { font: 700 13px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #365370; }
        .outputText { font: 700 14px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #1E3550; }
        .small { font: 600 12px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #5C708A; }
        .footerTitle { font: 700 18px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #183153; }
        .footerText { font: 500 14px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #365370; }
        .num { font: 700 16px 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif; fill: #FFFFFF; }
      </style>
    </defs>
    <rect x="0" y="0" width="1600" height="900" fill="url(#bgGrad)"></rect>
    <text x="60" y="68" class="title">說服醫生的整個流程架構</text>
    <text x="60" y="98" class="subtitle">以「客觀證據 → 醫師洞察 → 臨床重構 → 合規溝通 → 文案 → 簡報」形成完整轉化流程</text>
    <g transform="translate(60,125)">
      <rect x="0" y="0" rx="18" ry="18" width="132" height="36" fill="#E5F0FF" stroke="#C7DAFF"></rect>
      <text x="66" y="23" text-anchor="middle" class="chipText">客觀事實</text>
      <rect x="148" y="0" rx="18" ry="18" width="132" height="36" fill="#E7F8F6" stroke="#BEEBE5"></rect>
      <text x="214" y="23" text-anchor="middle" class="chipText">醫師洞察</text>
      <rect x="296" y="0" rx="18" ry="18" width="132" height="36" fill="#F1ECFF" stroke="#DDD1FF"></rect>
      <text x="362" y="23" text-anchor="middle" class="chipText">臨床價值</text>
      <rect x="444" y="0" rx="18" ry="18" width="160" height="36" fill="#FFEFE8" stroke="#FFD4C2"></rect>
      <text x="524" y="23" text-anchor="middle" class="chipText">合法合規轉化</text>
    </g>
    <g stroke="#5B7CF0" stroke-width="5" fill="none" marker-end="url(#arrow)" opacity="0.95">
      <line x1="260" y1="390" x2="290" y2="390"></line>
      <line x1="510" y1="390" x2="540" y2="390"></line>
      <line x1="760" y1="390" x2="790" y2="390"></line>
      <line x1="1010" y1="390" x2="1040" y2="390"></line>
      <line x1="1260" y1="390" x2="1290" y2="390"></line>
    </g>
    <g filter="url(#shadow)">
      <rect x="40" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="40" y="190" rx="22" ry="22" width="220" height="74" fill="#3B82F6"></rect>
      <circle cx="72" cy="227" r="18" fill="#215FD1"></circle>
      <text x="72" y="233" text-anchor="middle" class="num">1</text>
      <text x="100" y="235" class="cardTitle">概念對齊</text>
      <text x="58" y="300" class="cardBody">
        <tspan x="58" dy="0">• 盤點各藥品客觀事實</tspan>
        <tspan x="58" dy="25">• 整理機轉、適應症、</tspan>
        <tspan x="72" dy="22">安全性與療效證據</tspan>
        <tspan x="58" dy="25">• 比較競品差異</tspan>
        <tspan x="58" dy="25">• 找出 unique selling point</tspan>
        <tspan x="72" dy="22">(USP)</tspan>
      </text>
      <rect x="58" y="548" rx="14" ry="14" width="184" height="46" fill="#EEF5FF" stroke="#D2E2FF"></rect>
      <text x="78" y="567" class="outputLabel">輸出成果</text>
      <text x="78" y="586" class="outputText">核心訊息地圖</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="290" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="290" y="190" rx="22" ry="22" width="220" height="74" fill="#14B8A6"></rect>
      <circle cx="322" cy="227" r="18" fill="#0A8C7E"></circle>
      <text x="322" y="233" text-anchor="middle" class="num">2</text>
      <text x="350" y="235" class="cardTitle">角色扮演醫生</text>
      <text x="308" y="300" class="cardBody">
        <tspan x="308" dy="0">• 建立醫師 persona</tspan>
        <tspan x="308" dy="25">• 定義科別、資歷、場域</tspan>
        <tspan x="308" dy="25">• 模擬臨床情境與提問</tspan>
        <tspan x="308" dy="25">• 預判疑慮與決策障礙</tspan>
        <tspan x="308" dy="25">• 辨識真正在意的價值</tspan>
      </text>
      <rect x="308" y="548" rx="14" ry="14" width="184" height="46" fill="#EAFBF8" stroke="#C6F0E9"></rect>
      <text x="328" y="567" class="outputLabel">輸出成果</text>
      <text x="328" y="586" class="outputText">醫師洞察摘要</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="540" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="540" y="190" rx="22" ry="22" width="220" height="74" fill="#8B5CF6"></rect>
      <circle cx="572" cy="227" r="18" fill="#6D37EA"></circle>
      <text x="572" y="233" text-anchor="middle" class="num">3</text>
      <text x="600" y="226" class="cardTitle">說服策略</text>
      <text x="600" y="248" class="small" fill="#F3EAFF">(Clinical Reframing)</text>
      <text x="558" y="300" class="cardBody">
        <tspan x="558" dy="0">• 將產品優勢轉為</tspan>
        <tspan x="572" dy="22">臨床價值語言</tspan>
        <tspan x="558" dy="25">• 對應痛點與未滿足需求</tspan>
        <tspan x="558" dy="25">• 串接指引、研究與 RWE</tspan>
        <tspan x="558" dy="25">• 建立說服主軸與順序</tspan>
      </text>
      <rect x="558" y="548" rx="14" ry="14" width="184" height="46" fill="#F4F0FF" stroke="#E0D5FF"></rect>
      <text x="578" y="567" class="outputLabel">輸出成果</text>
      <text x="578" y="586" class="outputText">臨床說服框架</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="790" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="790" y="190" rx="22" ry="22" width="220" height="74" fill="#F97316"></rect>
      <circle cx="822" cy="227" r="18" fill="#DC5D09"></circle>
      <text x="822" y="233" text-anchor="middle" class="num">4</text>
      <text x="850" y="226" class="cardTitle">合法高轉換</text>
      <text x="850" y="248" class="small" fill="#FFF2E8">溝通策略</text>
      <text x="808" y="300" class="cardBody">
        <tspan x="808" dy="0">• 依醫師主要客群分眾</tspan>
        <tspan x="808" dy="25">• 設計合規對話路徑</tspan>
        <tspan x="808" dy="25">• 平衡利益與風險揭露</tspan>
        <tspan x="808" dy="25">• 安排提問節奏與 CTA</tspan>
        <tspan x="808" dy="25">• 兼顧轉換與信任建立</tspan>
      </text>
      <rect x="808" y="548" rx="14" ry="14" width="184" height="46" fill="#FFF2EA" stroke="#FFD8C0"></rect>
      <text x="828" y="567" class="outputLabel">輸出成果</text>
      <text x="828" y="586" class="outputText">溝通路徑設計</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="1040" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="1040" y="190" rx="22" ry="22" width="220" height="74" fill="#EC4899"></rect>
      <circle cx="1072" cy="227" r="18" fill="#D61F7B"></circle>
      <text x="1072" y="233" text-anchor="middle" class="num">5</text>
      <text x="1100" y="235" class="cardTitle">設計溝通文案</text>
      <text x="1058" y="300" class="cardBody">
        <tspan x="1058" dy="0">• 設計開場句與破題角度</tspan>
        <tspan x="1058" dy="25">• 編排關鍵訊息與證據點</tspan>
        <tspan x="1058" dy="25">• 準備反對意見回應</tspan>
        <tspan x="1058" dy="25">• 撰寫結尾與 follow-up</tspan>
        <tspan x="1058" dy="25">• 形成可實戰話術腳本</tspan>
      </text>
      <rect x="1058" y="548" rx="14" ry="14" width="184" height="46" fill="#FFF0F7" stroke="#FFD0E5"></rect>
      <text x="1078" y="567" class="outputLabel">輸出成果</text>
      <text x="1078" y="586" class="outputText">溝通文案腳本</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="1290" y="190" rx="22" ry="22" width="220" height="430" fill="#FFFFFF"></rect>
      <rect x="1290" y="190" rx="22" ry="22" width="220" height="74" fill="#2563EB"></rect>
      <circle cx="1322" cy="227" r="18" fill="#1747B5"></circle>
      <text x="1322" y="233" text-anchor="middle" class="num">6</text>
      <text x="1350" y="235" class="cardTitle">最終簡報</text>
      <text x="1308" y="300" class="cardBody">
        <tspan x="1308" dy="0">• 一頁一重點</tspan>
        <tspan x="1308" dy="25">• 視覺化關鍵臨床證據</tspan>
        <tspan x="1308" dy="25">• 以醫師場景組織內容</tspan>
        <tspan x="1308" dy="25">• 放入行動建議與下一步</tspan>
        <tspan x="1308" dy="25">• 完成可執行簡報版本</tspan>
      </text>
      <rect x="1308" y="548" rx="14" ry="14" width="184" height="46" fill="#EEF4FF" stroke="#D4E0FF"></rect>
      <text x="1328" y="567" class="outputLabel">輸出成果</text>
      <text x="1328" y="586" class="outputText">最終提案簡報</text>
    </g>
    <g filter="url(#shadow)">
      <rect x="60" y="690" width="1480" height="150" rx="26" ry="26" fill="#FFFFFF"></rect>
      <text x="90" y="735" class="footerTitle">驗證與迭代機制</text>
      <text x="90" y="763" class="footerText">整個流程不是線性結束,而是持續回圈:先用角色扮演驗證,再做合規審查,持續優化文案與簡報。</text>
      <g transform="translate(90,790)">
        <rect x="0" y="-18" width="230" height="42" rx="18" ry="18" fill="#EAF2FF" stroke="#D0DEFF"></rect>
        <text x="115" y="8" text-anchor="middle" class="footerText">角色扮演測試</text>
        <line x1="230" y1="3" x2="285" y2="3" stroke="#88A6F8" stroke-width="4" marker-end="url(#arrow)"></line>
        <rect x="300" y="-18" width="230" height="42" rx="18" ry="18" fill="#EAFBF8" stroke="#C6F0E9"></rect>
        <text x="415" y="8" text-anchor="middle" class="footerText">法規 / 醫藥合規審查</text>
        <line x1="530" y1="3" x2="585" y2="3" stroke="#88A6F8" stroke-width="4" marker-end="url(#arrow)"></line>
        <rect x="600" y="-18" width="230" height="42" rx="18" ry="18" fill="#F4F0FF" stroke="#E0D5FF"></rect>
        <text x="715" y="8" text-anchor="middle" class="footerText">文案優化與 A/B 修正</text>
        <line x1="830" y1="3" x2="885" y2="3" stroke="#88A6F8" stroke-width="4" marker-end="url(#arrow)"></line>
        <rect x="900" y="-18" width="230" height="42" rx="18" ry="18" fill="#FFF2EA" stroke="#FFD8C0"></rect>
        <text x="1015" y="8" text-anchor="middle" class="footerText">簡報更新與再輸出</text>
        <path d="M1138,3 C1185,3 1215,3 1248,3 C1300,3 1300,-55 1248,-55 L78,-55 C30,-55 30,-5 78,-5" fill="none" stroke="#A9BDFB" stroke-width="3.5" stroke-dasharray="8 8" marker-end="url(#arrow)"></path>
      </g>
    </g>
    <text x="60" y="870" class="small">建議使用情境:醫藥行銷、學術溝通、產品定位、醫師簡報製作。</text>
  </svg>
  ```

  上方為流程主體圖,六張卡片分別對應六個階段(概念對齊 → 角色扮演 → 說服策略 → 合法溝通 → 設計文案 → 簡報),底部一條虛線回路代表持續迭代。
  點 graph / code 按鈕可切換看圖或看 SVG markup;檔案約 12 KB,接近但未超過 16 KB 內聯閾值。

- **#why-not-png** `type:note`

  把這張圖以 inline SVG 而非 PNG 給 Markdown+,理由:
  - SVG 內 `<text>` 對 AI 是可讀的詞彙(`角色扮演醫生`、`合規對話路徑`),PNG 對 AI 等於沒內容
  - 自動關鍵詞抽取會把 SVG 內的概念詞納入計算
  - 12 KB 仍在 viewer 可接受範圍,不必拆檔
