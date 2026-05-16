"""
Markdown+ playground server.

Serves the static site under `public/` and proxies the rewriter to OpenAI's
Responses API. The OpenAI key is read from the OPENAI_API_KEY environment
variable on the server side and never exposed to the browser.

Deployment:
    - Local:    set OPENAI_API_KEY=sk-...   then `python server.py`
    - Zeabur:   set OPENAI_API_KEY in the project's env vars; Zeabur sets PORT;
                start command is `python server.py` (or use the included Procfile).
    - Docker:   `docker build -t markdown-plus . && docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 markdown-plus`

Environment variables:
    OPENAI_API_KEY     required for /api/rewrite to function
    PORT               port to listen on (default 8000; Zeabur sets this automatically)
    HOST               bind host (default 0.0.0.0)
    REWRITER_MODEL     default: gpt-5.4-mini
    REWRITER_EFFORT    default: none

Endpoints:
    GET  /                       → public/index.html
    GET  /<path>                 → public/<path>
    GET  /api/health             → JSON {ok, model, effort, has_key}
    POST /api/rewrite            → NDJSON stream (text/plain + X-Stream-Format: ndjson)
                                    body: {"from": "markdown"|"html", "content": str}
                                    events: {type:start}, {type:delta,delta}, {type:done,...}, {type:error,...}
    GET  /api/mdp/list           → JSON block manifest (params: path, depth, type, status, where, fields)
    GET  /api/mdp/tree           → JSON nested block hierarchy (params: path)
    GET  /api/mdp/get            → JSON one block's metadata (params: path, id)
    GET  /api/mdp/children       → JSON direct child ids (params: path, id)
    GET  /api/mdp/read           → JSON block body markdown (params: path, id, children, max_lines)
    GET  /api/mdp/search         → JSON keyword search over metadata (params: path, q, limit)
    GET  /api/mdp/xref           → JSON resolved relationships (params: path, id)

    The /api/mdp/* family is the Layer 2 block-query API: it lets an agent do
    progressive disclosure over a Markdown+ doc instead of reading the whole
    file. `path` is resolved relative to public/ and may not escape it.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
PROMPTS_DIR = ROOT / "prompts"

PROMPTS: dict[str, Path] = {
    "markdown": PROMPTS_DIR / "from_markdown.txt",
    "html":     PROMPTS_DIR / "from_html.txt",
}

MODEL = os.environ.get("REWRITER_MODEL", "gpt-5.4-mini")
EFFORT = os.environ.get("REWRITER_EFFORT", "none")

# Block-query API (Layer 2) lives in cli/python/query.py — reuse it here so the
# HTTP endpoints and the offline CLI share one implementation.
sys.path.insert(0, str(ROOT / "cli" / "python"))
try:
    import query as mdp_query  # type: ignore
except Exception as _e:  # noqa: BLE001
    mdp_query = None
    _MDP_IMPORT_ERROR = str(_e)


def build_prompt(kind: str, content: str) -> str:
    tmpl = PROMPTS[kind].read_text(encoding="utf-8")
    placeholder = "{{markdown_doc}}" if kind == "markdown" else "{{html_doc}}"
    return tmpl.replace(placeholder, content)


class Handler(SimpleHTTPRequestHandler):
    # Serve static files from public/ (Zeabur convention)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/rewrite":
            return self.handle_rewrite()
        self.send_error(404, "endpoint not found")

    # ---- GET ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            return self.json_response(200, {
                "ok": True,
                "model": MODEL,
                "effort": EFFORT,
                "has_key": bool(os.environ.get("OPENAI_API_KEY")),
                "mdp_query": mdp_query is not None,
            })
        if path.startswith("/api/mdp/"):
            return self.handle_mdp(path, parse_qs(parsed.query))
        # Root → index.html
        if path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    # ---- /api/mdp/* — block-query API (Layer 2) ----
    def _safe_doc_path(self, raw: str) -> Path:
        """Resolve `raw` relative to public/ and reject anything that escapes it."""
        candidate = (PUBLIC_DIR / raw).resolve()
        if candidate != PUBLIC_DIR and not candidate.is_relative_to(PUBLIC_DIR):
            raise ValueError("path escapes the public/ directory")
        return candidate

    def handle_mdp(self, path: str, params: dict[str, list[str]]) -> None:
        if mdp_query is None:
            return self.json_response(500, {
                "error": f"block-query module unavailable: {_MDP_IMPORT_ERROR}"
            })
        op = path[len("/api/mdp/"):]

        def p(name: str, default=None):
            v = params.get(name)
            return v[0] if v else default

        raw_path = p("path")
        if not raw_path:
            return self.json_response(400, {"error": "missing 'path' query param"})
        try:
            doc = self._safe_doc_path(raw_path)
        except ValueError as e:
            return self.json_response(403, {"error": str(e)})
        if not doc.is_file():
            return self.json_response(404, {"error": f"file not found: {raw_path}"})

        def need_id():
            bid = p("id")
            if not bid:
                raise ValueError("missing 'id' query param")
            return bid

        try:
            if op == "list":
                depth = int(p("depth")) if p("depth") else None
                where: dict[str, str] = {}
                for key in ("type", "status", "parent"):
                    if p(key):
                        where[key] = p(key)
                for pair in params.get("where", []):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        where[k] = v
                fields = p("fields")
                result = mdp_query.list_blocks(
                    doc, depth=depth, where=where or None,
                    fields=fields.split(",") if fields else None,
                )
            elif op == "tree":
                result = mdp_query.tree(doc)
            elif op == "get":
                result = mdp_query.get_block_meta(doc, need_id())
            elif op == "children":
                result = mdp_query.list_children(doc, need_id())
            elif op == "read":
                max_lines = int(p("max_lines")) if p("max_lines") else None
                result = mdp_query.read_block(
                    doc, need_id(),
                    include_children=p("children", "") in ("1", "true", "yes"),
                    max_lines=max_lines,
                )
            elif op == "search":
                q = p("q")
                if not q:
                    return self.json_response(400, {"error": "missing 'q' query param"})
                result = mdp_query.search_blocks(
                    doc, q, limit=int(p("limit")) if p("limit") else 20,
                )
            elif op == "xref":
                result = mdp_query.resolve_xref(doc, need_id())
            else:
                return self.json_response(404, {"error": f"unknown mdp op: {op!r}"})
        except KeyError as e:
            return self.json_response(404, {"error": str(e).strip('"')})
        except ValueError as e:
            return self.json_response(400, {"error": str(e)})

        return self.json_response(200, {"ok": True, "op": op, "result": result})

    # ---- /api/rewrite handler — streams NDJSON ----
    def handle_rewrite(self):
        # ---- Pre-flight validation (still returns plain JSON on error) ----
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return self.json_response(400, {"error": "empty body"})
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return self.json_response(400, {"error": f"invalid JSON: {e}"})

        kind = data.get("from", "markdown")
        content = data.get("content", "")
        if kind not in PROMPTS:
            return self.json_response(400, {"error": f"unknown 'from': {kind!r}"})
        if not content.strip():
            return self.json_response(400, {"error": "content is empty"})
        if not os.environ.get("OPENAI_API_KEY"):
            return self.json_response(500, {
                "error": "OPENAI_API_KEY environment variable is not set. "
                         "Set it on the server (Zeabur env var panel or local shell) and restart."
            })

        try:
            from openai import OpenAI
        except ImportError:
            return self.json_response(500, {
                "error": "openai package is not installed. Run `pip install -r requirements.txt` and restart."
            })

        prompt = build_prompt(kind, content)
        client = OpenAI()
        headers_sent = False

        def write_ndjson(obj: dict) -> None:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            try:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # client disconnected

        try:
            with client.responses.stream(
                model=MODEL,
                input=prompt,
                reasoning={"effort": EFFORT},
            ) as stream:
                # text/plain + nosniff + custom marker keeps Chrome CORB
                # from blocking application/x-ndjson on cross-origin loads.
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Stream-Format", "ndjson")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")  # disable proxy buffering
                self.end_headers()
                headers_sent = True

                write_ndjson({"type": "start", "model": MODEL})

                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "response.output_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        if delta:
                            write_ndjson({"type": "delta", "delta": delta})

                final = stream.get_final_response()
                output_tokens = int(getattr(final.usage, "output_tokens", 0) or 0)
                write_ndjson({"type": "done", "model": MODEL, "output_tokens": output_tokens})

        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "error": f"{type(e).__name__}: {e}"}
            if headers_sent:
                write_ndjson(err)
            else:
                return self.json_response(500, {"error": err["error"]})

    # ---- helpers ----
    def json_response(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


def main() -> int:
    # PORT precedence: --port flag > PORT env var > default 8000
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    argv = sys.argv[1:]
    if "--port" in argv:
        i = argv.index("--port")
        port = int(argv[i + 1])

    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    print(f"Markdown+ server listening on http://{host}:{port}")
    print(f"  Root:    {PUBLIC_DIR}")
    print(f"  Prompts: {PROMPTS_DIR}")
    print(f"  Model:   {MODEL}  (reasoning effort: {EFFORT})")
    print(f"  API key: {'YES (from OPENAI_API_KEY env)' if has_key else 'MISSING — /api/rewrite will return 500'}")
    sys.stdout.flush()

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
