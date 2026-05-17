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
    POST /api/chat               → NDJSON stream — chat-with-document agent loop.
                                    body: {"doc": str (Markdown+ source),
                                           "messages": [{role,content,...}, ...]}
                                    events: start / iteration / tool_call / tool_result /
                                            delta / done / error
                                    The LLM has the 7 mdp_* tools auto-injected from
                                    tools/openai-function-defs.json; `path` is replaced
                                    with a per-request temp file so the model only picks
                                    block ids, queries, depths etc.
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

import copy
import inspect
import json
import os
import re
import sys
import tempfile
import uuid
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


# ---------------- Chat-with-document tool dispatcher ----------------
# The LLM gets the 7 mdp_* tools from tools/openai-function-defs.json. We strip
# `path` from the schema (so the model isn't allowed to pick a file) and inject
# the user's uploaded doc via a per-request temp file before executing.

TOOLS_JSON = ROOT / "tools" / "openai-function-defs.json"

# Maps tool name (mdp_*) → (function_name_in_query_module, arg_alias_map).
# arg_alias_map remaps the OpenAI-schema arg name to the Python function's
# parameter name when they differ (e.g. tool exposes `query`, function takes `q`).
_TOOL_DISPATCH: dict[str, tuple[str, dict[str, str]]] = {
    "mdp_list_blocks":    ("list_blocks",    {}),
    "mdp_get_block_meta": ("get_block_meta", {"id": "block_id"}),
    "mdp_list_children":  ("list_children",  {"id": "block_id"}),
    "mdp_read_block":     ("read_block",     {"id": "block_id"}),
    "mdp_search_blocks":  ("search_blocks",  {}),
    "mdp_resolve_xref":   ("resolve_xref",   {"id": "block_id"}),
    "mdp_tree":           ("tree",           {}),
}


def _load_chat_tools() -> list[dict] | None:
    """Load tool schemas with `path` stripped (we inject server-side)."""
    if not TOOLS_JSON.is_file():
        return None
    try:
        raw = json.loads(TOOLS_JSON.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    out: list[dict] = []
    for t in raw:
        ft = copy.deepcopy(t)
        params = ft.get("function", {}).get("parameters", {})
        props = params.get("properties", {})
        props.pop("path", None)
        if "required" in params:
            params["required"] = [r for r in params["required"] if r != "path"]
        out.append(ft)
    return out


def _execute_mdp_tool(tool_name: str, raw_args: dict, doc_path: Path) -> object:
    """Execute one tool call. Inject doc_path; remap arg names; tolerate bad json."""
    if mdp_query is None:
        return {"error": "block-query module unavailable"}
    if tool_name not in _TOOL_DISPATCH:
        return {"error": f"unknown tool: {tool_name}"}
    fn_name, alias_map = _TOOL_DISPATCH[tool_name]
    fn = getattr(mdp_query, fn_name, None)
    if fn is None:
        return {"error": f"function {fn_name} not found in query module"}

    # Remap arg names from schema → function signature
    args: dict = {"path": doc_path}
    for k, v in (raw_args or {}).items():
        args[alias_map.get(k, k)] = v

    # Drop any kwargs the function doesn't accept (LLM occasionally invents some)
    sig = inspect.signature(fn)
    valid = set(sig.parameters.keys())
    args = {k: v for k, v in args.items() if k in valid}

    try:
        return fn(**args)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _extract_usage(resp) -> tuple[int, int, int]:
    """Pull (prompt_tokens, cached_prompt_tokens, completion_tokens) out of an
    OpenAI ChatCompletion response. `cached_tokens` lives under
    usage.prompt_tokens_details.cached_tokens — present on gpt-4o family when
    prompt caching kicks in (auto for prompts ≥ 1024 tok with matching prefix,
    50% input discount). Returns 0s if any field is missing."""
    usage = getattr(resp, "usage", None)
    if not usage:
        return 0, 0, 0
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    return in_tok, cached, out_tok


def build_prompt(kind: str, content: str) -> str:
    tmpl = PROMPTS[kind].read_text(encoding="utf-8")
    placeholder = "{{markdown_doc}}" if kind == "markdown" else "{{html_doc}}"
    return tmpl.replace(placeholder, content)


# Pre-clean rules:
#   - HTML: strip <script>/<style> blocks (token waste + defense) and on*= event
#     handlers (the prompt asks the LLM to do this, but doing it server-side
#     before the LLM sees the content is cheaper and removes one failure mode).
#   - Markdown: no pre-clean — markdown rarely carries executable content; if
#     the user pastes HTML-inside-markdown, the same rules apply on the way
#     out of the LLM anyway.
_HTML_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.DOTALL | re.IGNORECASE)
_HTML_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.DOTALL | re.IGNORECASE)
_HTML_ON_HANDLER_RE = re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE)


def pre_clean(kind: str, content: str) -> tuple[str, dict]:
    """Return (cleaned_content, stats). stats is included in the start event."""
    stats: dict[str, int] = {}
    if kind == "html":
        new, n = _HTML_SCRIPT_RE.subn("", content)
        if n:
            stats["stripped_script_blocks"] = n
            content = new
        new, n = _HTML_STYLE_RE.subn("", content)
        if n:
            stats["stripped_style_blocks"] = n
            content = new
        new, n = _HTML_ON_HANDLER_RE.subn("", content)
        if n:
            stats["stripped_event_handlers"] = n
            content = new
    return content, stats


# Post-clean: strip a single leading ```{lang}? ... ``` wrapper if the LLM
# violated "do not wrap output in a code fence". Idempotent and conservative:
# only strips when both ends look like a wrapper around the whole output.
_LEADING_FENCE_RE = re.compile(r"^\s*```[a-zA-Z+\-]*\s*\n")
_TRAILING_FENCE_RE = re.compile(r"\n```\s*$")


def post_clean(text: str) -> tuple[str, bool]:
    """Return (cleaned, was_wrapped)."""
    stripped_text = text
    if _LEADING_FENCE_RE.search(text) and _TRAILING_FENCE_RE.search(text):
        stripped_text = _LEADING_FENCE_RE.sub("", text, count=1)
        stripped_text = _TRAILING_FENCE_RE.sub("", stripped_text, count=1)
        return stripped_text, True
    return text, False


# Lazy: only imported when /api/rewrite is hit (keeps cold-start cheap).
_mdp_validator = None


def _load_validator():
    global _mdp_validator
    if _mdp_validator is None:
        try:
            import validator as v  # type: ignore
            _mdp_validator = v
        except Exception:  # noqa: BLE001
            _mdp_validator = False  # mark as failed so we don't retry
    return _mdp_validator or None


class Handler(SimpleHTTPRequestHandler):
    # Serve static files from public/ (Zeabur convention)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/rewrite":
            return self.handle_rewrite()
        if path == "/api/chat":
            return self.handle_chat()
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
                "chat_tools": (
                    len(_load_chat_tools() or [])
                    if (TOOLS_JSON.is_file() and mdp_query is not None)
                    else 0
                ),
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

        # ---- Pre-clean (server-side, before LLM) ----
        content, pre_stats = pre_clean(kind, content)

        prompt = build_prompt(kind, content)
        client = OpenAI()
        headers_sent = False
        accumulated: list[str] = []  # for post-clean + validation

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

                start_msg: dict = {"type": "start", "model": MODEL}
                if pre_stats:
                    start_msg["pre_clean"] = pre_stats
                write_ndjson(start_msg)

                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "response.output_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        if delta:
                            accumulated.append(delta)
                            write_ndjson({"type": "delta", "delta": delta})

                final = stream.get_final_response()
                output_tokens = int(getattr(final.usage, "output_tokens", 0) or 0)

                # ---- Post-clean: detect fence wrapper (the LLM occasionally violates
                # "don't wrap output in code fence"). We do NOT mutate what the client
                # already received via streaming — just tell the client to strip it.
                full_text = "".join(accumulated)
                _, was_wrapped = post_clean(full_text)

                # ---- Validation: run validator on output and include summary so the
                # client can show a server-confirmed lint result alongside its own.
                lint_summary: dict | None = None
                v = _load_validator()
                if v is not None:
                    try:
                        cleaned_for_lint, _ = post_clean(full_text)
                        _, issues = v.validate(cleaned_for_lint)
                        errs = [i for i in issues if i.severity == "error"]
                        warns = [i for i in issues if i.severity == "warning"]
                        lint_summary = {
                            "errors": len(errs),
                            "warnings": len(warns),
                            # First few error codes so client can hint at what's wrong
                            "sample_codes": list({i.code for i in errs[:5]}) or None,
                        }
                    except Exception:  # noqa: BLE001
                        lint_summary = {"error": "validator failed"}

                done_msg: dict = {
                    "type": "done",
                    "model": MODEL,
                    "output_tokens": output_tokens,
                    "wrapped_in_fence": was_wrapped,  # client should strip if true
                }
                if lint_summary is not None:
                    done_msg["lint"] = lint_summary
                write_ndjson(done_msg)

        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "error": f"{type(e).__name__}: {e}"}
            if headers_sent:
                write_ndjson(err)
            else:
                return self.json_response(500, {"error": err["error"]})

    # ---- /api/chat — agent loop over Markdown+ document with mdp_* tools ----
    # Body: {"doc": "<full Markdown+ source>", "messages": [{role, content}, ...]}
    # Streams NDJSON with event types:
    #   {type:"start", model, tools_loaded}
    #   {type:"iteration", n}
    #   {type:"tool_call", id, name, args}
    #   {type:"tool_result", id, ok, result|error}
    #   {type:"delta", delta}           — assistant text chunks
    #   {type:"done", iterations, tool_calls, input_tokens, cached_tokens, output_tokens}
    #   {type:"error", error}
    MAX_AGENT_ITERATIONS = 15

    def handle_chat(self):
        # ---- Validate body ----
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return self.json_response(400, {"error": "empty body"})
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            return self.json_response(400, {"error": f"invalid JSON: {e}"})

        doc = data.get("doc", "")
        history = data.get("messages") or []
        # mode = "blocks" (default — Markdown+ tool-loop) or "plain" (head-N-lines baseline)
        mode = data.get("mode", "blocks")
        if mode not in ("blocks", "plain"):
            return self.json_response(400, {"error": f"unknown mode: {mode!r}"})
        if not doc.strip():
            return self.json_response(400, {"error": "doc is empty"})
        if not isinstance(history, list) or not history:
            return self.json_response(400, {"error": "messages must be a non-empty list"})
        if not os.environ.get("OPENAI_API_KEY"):
            return self.json_response(500, {"error": "OPENAI_API_KEY not set"})

        tools = _load_chat_tools() if mode == "blocks" else None
        if mode == "blocks" and tools is None:
            return self.json_response(500, {"error": "tools schema unavailable"})

        try:
            from openai import OpenAI
        except ImportError:
            return self.json_response(500, {"error": "openai package missing"})

        client = OpenAI()
        headers_sent = False

        # Persist doc to a temp file inside the repo so cli/python/query.py can
        # parse it via Path (its API is path-based). Cleaned up at end.
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".chat.mdp.md",
            dir=str(ROOT), delete=False,
        )
        try:
            tmp.write(doc)
            tmp.close()
            doc_path = Path(tmp.name)

            def write_ndjson(obj: dict) -> None:
                nonlocal headers_sent
                if not headers_sent:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Stream-Format", "ndjson")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    headers_sent = True
                try:
                    self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            # ===== Plain Markdown baseline =====
            # No tools. The LLM gets only the first `head_lines` lines of the
            # raw document inline in the system prompt and must answer from
            # whatever is visible there — this is the "no progressive disclosure"
            # contrast condition the project benchmarks against.
            if mode == "plain":
                try:
                    head_lines = int(data.get("head_lines") or 200)
                except (TypeError, ValueError):
                    head_lines = 200
                head_lines = max(10, min(2000, head_lines))
                doc_lines = doc.splitlines()
                truncated = len(doc_lines) > head_lines
                head_text = "\n".join(doc_lines[:head_lines])
                shown = min(len(doc_lines), head_lines)
                plain_system = (
                    "You are answering questions about a Markdown document. "
                    "You have NO tools. The document below is shown to you as "
                    f"its first {shown} of {len(doc_lines)} lines"
                    + (" (TRUNCATED — content beyond this point is not visible to you). "
                       if truncated else " (complete). ")
                    + "Answer only from what is actually shown. If the answer "
                    + "would require lines you cannot see, say so explicitly.\n\n"
                    + "--- DOCUMENT (head only) ---\n"
                    + head_text
                )
                messages = [{"role": "system", "content": plain_system}]
                messages.extend(history)

                write_ndjson({
                    "type": "start",
                    "model": MODEL,
                    "tools_loaded": 0,
                    "mode": "plain",
                    "head_lines": shown,
                    "total_lines": len(doc_lines),
                    "truncated": truncated,
                })

                resp = client.chat.completions.create(model=MODEL, messages=messages)
                in_tok, cached_tok, out_tok = _extract_usage(resp)
                final_text = (resp.choices[0].message.content or "")
                if final_text:
                    write_ndjson({"type": "delta", "delta": final_text})
                write_ndjson({
                    "type": "done",
                    "iterations": 1,
                    "tool_calls": 0,
                    "input_tokens": in_tok,
                    "cached_tokens": cached_tok,
                    "output_tokens": out_tok,
                    "final_text_len": len(final_text),
                })
                return

            # ===== Markdown+ tool-loop mode (default) =====
            # Light system prompt so the LLM understands the document context.
            messages: list[dict] = [
                {"role": "system", "content": (
                    "You are answering questions about a Markdown+ document the user uploaded. "
                    "Always use the mdp_* tools to inspect the document — start with mdp_list_blocks "
                    "to see what's available, then mdp_get_block_meta or mdp_read_block on specific "
                    "block ids. Don't guess the document's content. Cite block ids in your answer "
                    "(e.g. \"`#decision-canary` says ...\"). Keep answers concise unless asked otherwise."
                )},
            ]
            messages.extend(history)

            write_ndjson({"type": "start", "model": MODEL, "tools_loaded": len(tools), "mode": "blocks"})

            total_tool_calls = 0
            total_input_tokens = 0
            total_cached_tokens = 0
            total_output_tokens = 0
            final_text = ""
            for it in range(1, self.MAX_AGENT_ITERATIONS + 1):
                write_ndjson({"type": "iteration", "n": it})

                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                in_tok, cached_tok, out_tok = _extract_usage(resp)
                total_input_tokens += in_tok
                total_cached_tokens += cached_tok
                total_output_tokens += out_tok

                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []

                if tool_calls:
                    # Append assistant turn that requested the tools
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            } for tc in tool_calls
                        ],
                    })
                    for tc in tool_calls:
                        total_tool_calls += 1
                        name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError as e:
                            args = {"_parse_error": str(e), "_raw": tc.function.arguments}
                        write_ndjson({"type": "tool_call", "id": tc.id, "name": name, "args": args})

                        result = _execute_mdp_tool(name, args, doc_path)
                        # NDJSON-safe: result may be list/dict/scalar
                        is_err = isinstance(result, dict) and "error" in result
                        write_ndjson({
                            "type": "tool_result",
                            "id": tc.id,
                            "name": name,
                            "ok": not is_err,
                            "result": result,
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        })
                    continue  # loop with tool results in context

                # Final assistant text
                final_text = msg.content or ""
                if final_text:
                    # Emit in one chunk; chat.completions wasn't streamed.
                    write_ndjson({"type": "delta", "delta": final_text})
                write_ndjson({
                    "type": "done",
                    "iterations": it,
                    "tool_calls": total_tool_calls,
                    "input_tokens": total_input_tokens,
                    "cached_tokens": total_cached_tokens,
                    "output_tokens": total_output_tokens,
                    "final_text_len": len(final_text),
                })
                return

            # Hit iteration cap — bail with what we have
            write_ndjson({
                "type": "error",
                "error": f"agent loop exceeded {self.MAX_AGENT_ITERATIONS} iterations",
            })
        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "error": f"{type(e).__name__}: {e}"}
            if headers_sent:
                try:
                    self.wfile.write((json.dumps(err) + "\n").encode("utf-8"))
                    self.wfile.flush()
                except Exception:  # noqa: BLE001
                    pass
            else:
                return self.json_response(500, {"error": err["error"]})
        finally:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

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
