# 部署到 Zeabur

## 前提

- 已有 [Zeabur](https://zeabur.com/) 帳號
- 已 fork 或 push 此 repo 到自己的 GitHub
- 已有有效的 OpenAI API key

## 步驟

### 1. 在 Zeabur 建立 Service

1. 進 Zeabur dashboard → 「Create Project」
2. 點 「Add Service」 → 「Deploy from GitHub」
3. 選你 fork 的 `markdown_plus` repo
4. Zeabur 會自動偵測 Python 專案,看到:
   - `requirements.txt` → 知道要 `pip install`
   - `Procfile` 或 `zeabur.json` → 知道 start command 是 `python server.py`
   - `runtime.txt` → 知道用 Python 3.11

### 2. 設定環境變數(關鍵)

在 service 的 **Variables** 區塊新增:

| Key | Value | 必填 |
|---|---|---|
| `OPENAI_API_KEY` | `sk-...`(你的 OpenAI key) | ✅ |
| `REWRITER_MODEL` | `gpt-5.4-mini`(預設) | optional |
| `REWRITER_EFFORT` | `none`(預設) | optional |

> ⚠️ **`OPENAI_API_KEY` 是 secret**,設定時記得勾「Hidden」/「Secret」選項。Zeabur 會把它注入到 server 環境變數,**不會送到瀏覽器**。

### 3. 等待部署

Build log 會顯示:
```
Installing dependencies from requirements.txt ...
Collecting openai>=1.60.0 ...
Starting: python server.py
Markdown+ server listening on http://0.0.0.0:<PORT>
  Root:    /app/public
  Prompts: /app/prompts
  Model:   gpt-5.4-mini  (reasoning effort: none)
  API key: YES (from OPENAI_API_KEY env)
```

### 4. 綁定 domain

Zeabur 預設給你一個 `*.zeabur.app` 子網域,點開即用。要綁自訂 domain:
1. Service → Settings → Domains → Generate Domain(免費 zeabur.app)
2. 或 Settings → Domains → Add Custom Domain → 跟著 DNS 設定指示

### 5. 驗證

開瀏覽器到部署的 domain,應該看到 index 頁。點到 playground:
- Rewriter tab 上方狀態 pill 顯示綠色「改寫服務就緒 · model: gpt-5.4-mini」
- 改寫按鈕可點(不灰)
- 貼一段 markdown 試改寫,字串會即時 streaming 跑出來

## 換 model

要換成 `gpt-5.5`(更貴更強)或 `gpt-4o-mini`(便宜) 等,改 Zeabur env var `REWRITER_MODEL` 重啟即可。

## 健康檢查

```
GET /api/health
```
回應:
```json
{"ok": true, "model": "gpt-5.4-mini", "effort": "none", "has_key": true}
```

`has_key` 若是 `false`,代表 `OPENAI_API_KEY` 沒設或拼錯。

## 為什麼 OPENAI_API_KEY 在 server 端

- **絕對不能放前端**:任何人 view source 就會看到
- **絕對不能在 query string 傳**:會被 log 在 nginx、CDN、history 各處
- 唯一安全選項:後端讀 env var,前端只跟後端講話

`server.py` 的 `/api/rewrite` 是 proxy — 收到瀏覽器的 markdown content,在 server 端用 env 裡的 key 呼叫 OpenAI,把 stream 結果轉成 NDJSON 給前端。Key 永遠不離開 server。

## 部署 troubleshooting

| 症狀 | 可能原因 | 修法 |
|---|---|---|
| `/api/health` 回 500 | `pip install` 失敗 | 看 Zeabur build log 是否有錯 |
| `has_key: false` | env var 沒設或拼錯 | 確認 `OPENAI_API_KEY` 一字不差 |
| 改寫一直 hang | model 名稱錯 / OpenAI 限流 | 換成 `gpt-4o-mini` 試試;確認帳戶有額度 |
| 瀏覽器 console 顯示 CORB | 不應出現(同源呼叫) | 確認你開的是 zeabur domain,不是 file:// |
| 第一次改寫等很久 | 冷啟動 + LLM thinking | 正常,第一個 token 通常 5–15 秒;之後 streaming 順暢 |
| 部署在 Zeabur 但 PORT 連不上 | 沒讀 `PORT` env var | `server.py` 已內建讀 PORT env,確認沒被改 |
