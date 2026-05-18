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
    POST /api/tokens             → JSON {tokens, encoding, estimated}
                                    body: {"text": str}
                                    Counts tokens with tiktoken (o200k_base) when
                                    available; falls back to a CJK-aware heuristic
                                    and marks estimated=true.

    The /api/mdp/* family is the Layer 2 block-query API: it lets an agent do
    progressive disclosure over a Markdown+ doc instead of reading the whole
    file. `path` is resolved relative to public/ and may not escape it.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import inspect
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
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

_PLAIN_BASH_TOOL: dict = {
    "type": "function",
    "name": "bash",
    "description": (
        "Run a read-only bash command in a temporary directory containing "
        "document.md. Use normal CLI tools such as grep -n, sed -n, awk, "
        "head, tail, wc, nl -ba, or a small read-only python3 heredoc to "
        "inspect the plain Markdown file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Bash command to run. The file is available as document.md "
                    "and as $DOC_PATH. Prefer read-only commands; do not write "
                    "files or access the network. Python heredocs may only read "
                    "document.md and print derived output."
                ),
            }
        },
        "required": ["command"],
        "additionalProperties": False,
    },
}

_BASH_DENY_RE = re.compile(
    r"(\$\(|`|(?<![=!<>])>>?(?![=])|<\(|\b(rm|mv|cp|chmod|chown|dd|mkfs|mount|umount|"
    r"curl|wget|ssh|scp|ftp|nc|ncat|telnet|python|python3|node|perl|"
    r"ruby|php|powershell|pwsh|cmd|git|pip|npm|pnpm|yarn)\b)",
    re.IGNORECASE,
)


def _limit_tool_text(s: str, n: int = 12000) -> tuple[str, bool]:
    if len(s) <= n:
        return s, False
    return s[:n] + "\n...[truncated]...", True


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


def _is_doc_arg(arg: str) -> bool:
    normalized = arg.strip("\"'")
    return normalized in {"document.md", "./document.md", "$DOC_PATH", "${DOC_PATH}"}


def _strip_doc_args(args: list[str]) -> list[str]:
    return [a for a in args if not _is_doc_arg(a)]


def _plain_cli_source(args: list[str], stdin_lines: list[str] | None, doc_lines: list[str]) -> tuple[list[str], list[str]]:
    return (doc_lines, _strip_doc_args(args)) if any(_is_doc_arg(a) for a in args) or stdin_lines is None else (stdin_lines, args)


def _run_plain_cli_segment(segment: str, stdin_lines: list[str] | None, doc_lines: list[str]) -> tuple[int, list[str], str]:
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError as e:
        return 2, [], f"parse error: {e}"
    if not argv:
        return 0, stdin_lines or [], ""

    cmd = argv[0]
    args = argv[1:]
    source, args = _plain_cli_source(args, stdin_lines, doc_lines)

    if cmd == "echo":
        return 0, [" ".join(args)], ""

    if cmd == "cat":
        if args:
            return 2, [], "cat fallback only supports document.md or piped input"
        return 0, source[:], ""

    if cmd == "nl":
        if args not in (["-ba"], ["-b", "a"], []):
            return 2, [], "nl fallback supports only: nl -ba document.md"
        return 0, [f"{i:>6}\t{line}" for i, line in enumerate(source, start=1)], ""

    if cmd == "wc":
        if args and args != ["-l"]:
            return 2, [], "wc fallback supports only: wc -l document.md"
        suffix = " document.md" if stdin_lines is None else ""
        return 0, [f"{len(source)}{suffix}"], ""

    if cmd in {"head", "tail"}:
        n = 10
        rest = args[:]
        if rest:
            if rest[0] == "-n" and len(rest) >= 2:
                try:
                    n = max(0, int(rest[1]))
                except ValueError:
                    return 2, [], f"{cmd}: invalid line count"
                rest = rest[2:]
            elif rest[0].startswith("-n") and len(rest[0]) > 2:
                try:
                    n = max(0, int(rest[0][2:]))
                except ValueError:
                    return 2, [], f"{cmd}: invalid line count"
                rest = rest[1:]
            elif re.fullmatch(r"-\d+", rest[0]):
                n = max(0, int(rest[0][1:]))
                rest = rest[1:]
        if rest:
            return 2, [], f"{cmd} fallback supports only -n N and document.md"
        return 0, (source[:n] if cmd == "head" else source[-n:] if n else []), ""

    if cmd == "sed":
        if len(args) < 2 or args[0] != "-n":
            return 2, [], "sed fallback supports only: sed -n 'A,Bp' document.md"
        expr = args[1]
        rest = args[2:]
        if rest:
            return 2, [], "sed fallback supports only one address expression and document.md"
        m = re.fullmatch(r"(\d+)(?:,(\d+))?p", expr.strip())
        if not m:
            return 2, [], "sed fallback supports only numeric print ranges like '120,180p'"
        start = int(m.group(1))
        end = int(m.group(2) or start)
        if end < start:
            start, end = end, start
        return 0, source[max(0, start - 1):end], ""

    if cmd == "grep":
        show_numbers = False
        ignore_case = False
        extended_regex = False
        rest: list[str] = []
        for a in args:
            if a == "-n":
                show_numbers = True
            elif a == "-i":
                ignore_case = True
            elif a == "-E":
                extended_regex = True
            elif a.startswith("-") and set(a[1:]).issubset({"n", "i", "E"}):
                show_numbers = show_numbers or "n" in a
                ignore_case = ignore_case or "i" in a
                extended_regex = extended_regex or "E" in a
            else:
                rest.append(a)
        if not rest:
            return 2, [], "grep fallback needs a pattern"
        pattern = rest[0]
        extra = _strip_doc_args(rest[1:])
        if extra:
            return 2, [], "grep fallback supports one pattern and document.md"
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags) if extended_regex else None
        except re.error as e:
            return 2, [], f"grep: invalid regex: {e}"
        needle = pattern.lower() if ignore_case and not regex else pattern
        out: list[str] = []
        for i, line in enumerate(source, start=1):
            hay = line.lower() if ignore_case and not regex else line
            matched = bool(regex.search(line)) if regex else needle in hay
            if matched:
                out.append(f"{i}:{line}" if show_numbers else line)
        return (0 if out else 1), out, ""

    if cmd == "awk":
        if not args:
            return 2, [], "awk fallback needs a simple NR range expression"
        expr = args[0].strip()
        rest = _strip_doc_args(args[1:])
        if rest:
            return 2, [], "awk fallback supports one expression and document.md"
        m = (
            re.search(r"NR\s*>=\s*(\d+)\s*&&\s*NR\s*<=\s*(\d+)", expr)
            or re.search(r"NR\s*==\s*(\d+)\s*,\s*NR\s*==\s*(\d+)", expr)
        )
        if not m:
            return 2, [], "awk fallback supports simple NR ranges, e.g. awk 'NR>=120 && NR<=180' document.md"
        start, end = int(m.group(1)), int(m.group(2))
        if end < start:
            start, end = end, start
        return 0, source[max(0, start - 1):end], ""

    return 127, [], f"unsupported fallback command: {cmd}"


def _split_into_statements(command: str) -> list[tuple[str | None, str]]:
    """Split a command line into statements joined by &&/||/; while respecting
    quotes and backslash escapes. Returns [(separator_to_previous, statement)].
    The first statement's separator is None. Single `|` (pipe) is left inside
    statements — the pipeline split happens later, per-statement."""
    out: list[tuple[str | None, str]] = []
    buf = ""
    sep: str | None = None
    i = 0
    in_quote: str | None = None
    n = len(command)
    while i < n:
        c = command[i]
        if in_quote:
            buf += c
            if c == in_quote:
                in_quote = None
            i += 1
            continue
        if c in ("'", '"'):
            in_quote = c
            buf += c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf += command[i:i + 2]
            i += 2
            continue
        if c == ";":
            out.append((sep, buf.strip()))
            buf = ""
            sep = ";"
            i += 1
            continue
        if c == "&" and i + 1 < n and command[i + 1] == "&":
            out.append((sep, buf.strip()))
            buf = ""
            sep = "&&"
            i += 2
            continue
        if c == "|" and i + 1 < n and command[i + 1] == "|":
            out.append((sep, buf.strip()))
            buf = ""
            sep = "||"
            i += 2
            continue
        buf += c
        i += 1
    if buf.strip() or sep:
        out.append((sep, buf.strip()))
    return [(s, stmt) for s, stmt in out if stmt or s in ("&&", "||", ";")]


def _split_pipeline(statement: str) -> list[str]:
    """Split a statement on top-level pipes while preserving quoted regex `|`."""
    segments: list[str] = []
    buf = ""
    i = 0
    in_quote: str | None = None
    n = len(statement)
    while i < n:
        c = statement[i]
        if in_quote:
            buf += c
            if c == in_quote:
                in_quote = None
            i += 1
            continue
        if c in ("'", '"'):
            in_quote = c
            buf += c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf += statement[i:i + 2]
            i += 2
            continue
        if c == "|" and not (i + 1 < n and statement[i + 1] == "|"):
            if buf.strip():
                segments.append(buf.strip())
            buf = ""
            i += 1
            continue
        buf += c
        i += 1
    if buf.strip():
        segments.append(buf.strip())
    return segments


_PYTHON_HEREDOC_RE = re.compile(
    r"^\s*(?:python3?|py)\s+-\s+<<(?P<quote>['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)\s*\r?\n(?P<code>[\s\S]*?)\r?\n(?P=tag)\s*$"
)

_PYTHON_DENY_NAMES = {
    "__import__", "breakpoint", "compile", "delattr", "dir", "eval", "exec",
    "getattr", "globals", "help", "input", "locals", "open", "setattr",
    "type", "vars",
}

_PYTHON_DENY_PATH_METHODS = {
    "chmod", "hardlink_to", "mkdir", "open", "rename", "replace", "rmdir",
    "symlink_to", "touch", "unlink", "write_bytes", "write_text",
}

_PYTHON_ALLOWED_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
}


class _ReadOnlyDocPath:
    def __init__(self, value: object, doc_text: str):
        normalized = str(value).replace("\\", "/").strip("\"'")
        if normalized not in {"document.md", "./document.md", "$DOC_PATH", "${DOC_PATH}"}:
            raise ValueError("read-only Python fallback may only open document.md")
        self._doc_text = doc_text

    def read_text(self, encoding: str = "utf-8", *args: object, **kwargs: object) -> str:
        if encoding and encoding.lower().replace("_", "-") != "utf-8":
            raise ValueError("read-only Python fallback supports only utf-8")
        return self._doc_text

    def exists(self) -> bool:
        return True

    def is_file(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "document.md"

    def __str__(self) -> str:
        return "document.md"


class _PlainPythonValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.error: str | None = None

    def fail(self, message: str) -> None:
        if self.error is None:
            self.error = message

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        allowed = {"re", "math", "statistics", "collections", "itertools"}
        for alias in node.names:
            if alias.name.split(".", 1)[0] not in allowed:
                self.fail(f"import not allowed in read-only Python fallback: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module != "pathlib" or any(alias.name != "Path" for alias in node.names):
            self.fail("read-only Python fallback only allows: from pathlib import Path")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if node.id.startswith("__") or node.id in _PYTHON_DENY_NAMES:
            self.fail(f"name not allowed in read-only Python fallback: {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr.startswith("__") or node.attr in _PYTHON_DENY_PATH_METHODS:
            self.fail(f"attribute not allowed in read-only Python fallback: {node.attr}")
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        self.fail("while loops are not allowed in read-only Python fallback")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.fail("function definitions are not allowed in read-only Python fallback")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.fail("function definitions are not allowed in read-only Python fallback")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.fail("class definitions are not allowed in read-only Python fallback")

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self.fail("lambda is not allowed in read-only Python fallback")


def _extract_python_heredoc(command: str) -> str | None:
    m = _PYTHON_HEREDOC_RE.match(command)
    return m.group("code") if m else None


def _execute_readonly_python_heredoc(command: str, source_doc_path: Path) -> object | None:
    code = _extract_python_heredoc(command)
    if code is None:
        return None
    doc_text = source_doc_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code, filename="<plain-cli-python>", mode="exec")
    except SyntaxError as e:
        return {
            "command": command,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"SyntaxError: {e}",
            "truncated": False,
            "fallback": "python-readonly-heredoc",
        }

    validator = _PlainPythonValidator()
    validator.visit(tree)
    if validator.error:
        return {
            "command": command,
            "exit_code": 2,
            "stdout": "",
            "stderr": validator.error,
            "truncated": False,
            "fallback": "python-readonly-heredoc",
        }

    def limited_import(name: str, globals_: object = None, locals_: object = None,
                       fromlist: tuple[str, ...] = (), level: int = 0) -> object:
        root_name = name.split(".", 1)[0]
        if name == "pathlib":
            return types.SimpleNamespace(Path=lambda value="document.md": _ReadOnlyDocPath(value, doc_text))
        if root_name in {"re", "math", "statistics", "collections", "itertools"}:
            return __import__(name, globals_, locals_, fromlist, level)
        raise ImportError(f"import not allowed: {name}")

    builtins = dict(_PYTHON_ALLOWED_BUILTINS)
    builtins["__import__"] = limited_import
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    globals_dict: dict[str, object] = {
        "__builtins__": builtins,
        "__name__": "__plain_cli_python__",
    }
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(compile(tree, "<plain-cli-python>", "exec"), globals_dict, globals_dict)
        exit_code = 0
    except Exception as e:  # noqa: BLE001
        exit_code = 1
        print(f"{type(e).__name__}: {e}", file=stderr_buf)

    stdout, out_trunc = _limit_tool_text(stdout_buf.getvalue())
    stderr, err_trunc = _limit_tool_text(stderr_buf.getvalue())
    return {
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_trunc or err_trunc,
        "fallback": "python-readonly-heredoc",
    }


def _execute_plain_cli_fallback(command: str, source_doc_path: Path) -> object:
    """Interpret a small read-only bash subset for Windows/no-bash environments.

    Supports statement chaining via `&&`, `||`, `;` at the top level (control
    flow follows bash conventions: `&&` runs only on success, `||` only on
    failure, `;` always). Within each statement, `|` still chains commands as
    a pipeline. Quoting/escaping is honored when splitting statements so a
    literal `&&` inside quotes is preserved as part of an argument."""
    doc_lines = source_doc_path.read_text(encoding="utf-8").splitlines()
    statements = _split_into_statements(command)
    if not statements:
        return {"error": "empty command"}

    last_exit = 0
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    for sep, statement in statements:
        # Bash short-circuit semantics for the operator joining this statement
        # to whatever ran before it.
        if sep == "&&" and last_exit != 0:
            continue
        if sep == "||" and last_exit == 0:
            continue
        if not statement:
            continue

        segments = _split_pipeline(statement)
        if not segments:
            continue

        stdin_lines: list[str] | None = None
        exit_code = 0
        for segment in segments:
            exit_code, stdin_lines, stderr = _run_plain_cli_segment(segment, stdin_lines, doc_lines)
            if stderr:
                stderr_chunks.append(stderr)
            if exit_code not in (0, 1):
                break

        stmt_out = "\n".join(stdin_lines or [])
        if stmt_out:
            stdout_chunks.append(stmt_out)
        last_exit = exit_code

    stdout_raw = "\n".join(stdout_chunks)
    if stdout_raw:
        stdout_raw += "\n"
    stderr_raw = "\n".join(stderr_chunks)
    stdout, out_trunc = _limit_tool_text(stdout_raw)
    stderr, err_trunc = _limit_tool_text(stderr_raw)
    return {
        "command": command,
        "exit_code": last_exit,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_trunc or err_trunc,
        "fallback": "python-readonly-cli",
    }


def _execute_plain_bash(raw_args: dict, source_doc_path: Path) -> object:
    """Run a constrained read-only bash command against a temp document.md."""
    command = str((raw_args or {}).get("command") or "").strip()
    if not command:
        return {"error": "missing command"}
    if len(command) > 1000:
        return {"error": "command too long; keep it under 1000 chars"}
    python_heredoc_result = _execute_readonly_python_heredoc(command, source_doc_path)
    if python_heredoc_result is not None:
        return python_heredoc_result
    if _BASH_DENY_RE.search(command):
        return {
            "error": (
                "command rejected by read-only guard; use grep/sed/awk/head/"
                "tail/wc/nl or a read-only python3 heredoc against document.md "
                "without network or file mutation"
            )
        }
    bash = shutil.which("bash")
    if not bash:
        return _execute_plain_cli_fallback(command, source_doc_path)
    if os.name == "nt" and str(Path(bash)).lower().endswith("\\windows\\system32\\bash.exe"):
        return _execute_plain_cli_fallback(command, source_doc_path)

    with tempfile.TemporaryDirectory(prefix="plain-cli-") as td:
        work_dir = Path(td)
        doc_path = work_dir / "document.md"
        doc_path.write_text(source_doc_path.read_text(encoding="utf-8"), encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "DOC_PATH": str(doc_path),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        try:
            p = subprocess.run(
                [bash, "--noprofile", "--norc", "-lc", command],
                cwd=str(work_dir),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8,
            )
        except subprocess.TimeoutExpired:
            return {"error": "command timed out after 8 seconds", "command": command}

    stdout, out_trunc = _limit_tool_text(p.stdout or "")
    stderr, err_trunc = _limit_tool_text(p.stderr or "")
    return {
        "command": command,
        "exit_code": p.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_trunc or err_trunc,
    }


# ---- Token counting (for /api/tokens) ----
# Lazy-loaded tiktoken encoder. `o200k_base` is the encoding used by GPT-4o /
# 4.1 / 5 families — matches the model the chat endpoint defaults to. When
# tiktoken isn't installed we fall back to a heuristic and mark the result as
# estimated so the UI can render a `≈` prefix.
_TIKTOKEN_ENC: object | None | bool = None  # None=untried, False=unavailable, encoder=ready


def _get_tiktoken_enc():
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is None:
        try:
            import tiktoken  # type: ignore
            _TIKTOKEN_ENC = tiktoken.get_encoding("o200k_base")
        except Exception:  # noqa: BLE001
            _TIKTOKEN_ENC = False
    return _TIKTOKEN_ENC if _TIKTOKEN_ENC is not False else None


def _count_tokens(text: str) -> tuple[int, bool]:
    """Return (token_count, estimated). Uses tiktoken o200k_base when available;
    otherwise approximates with: CJK chars ≈ 1 token each, other chars ≈ 4
    chars per token."""
    enc = _get_tiktoken_enc()
    if enc is not None:
        return len(enc.encode(text)), False
    cjk = 0
    for c in text:
        # U+3000–U+9FFF: CJK Symbols/Punctuation, Hiragana, Katakana, CJK Unified
        # U+AC00–U+D7AF: Hangul Syllables
        # U+FF00–U+FFEF: Halfwidth & Fullwidth Forms
        if ("　" <= c <= "鿿") or ("가" <= c <= "힯") or ("＀" <= c <= "￯"):
            cjk += 1
    other = len(text) - cjk
    return cjk + (other + 3) // 4, True


def _extract_usage(resp) -> tuple[int, int, int]:
    """Pull (input_tokens, cached_input_tokens, output_tokens) from an OpenAI
    response. Handles both shapes:
      - Responses API: usage.input_tokens / input_tokens_details.cached_tokens / output_tokens
      - Chat Completions: usage.prompt_tokens / prompt_tokens_details.cached_tokens / completion_tokens
    Cached tokens are populated whenever the chosen model supports prompt
    caching. Treat them as a subset of input tokens; pricing discounts are
    model-dependent, so the UI reports raw/cached counts instead of estimating
    currency or "effective" tokens."""
    usage = getattr(resp, "usage", None)
    if not usage:
        return 0, 0, 0
    in_tok = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "input_tokens_details", None) or getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    return in_tok, cached, out_tok


def _to_responses_tools(tools_chat_fmt: list[dict]) -> list[dict]:
    """Convert Chat Completions tool format (nested under "function": {...})
    to the Responses API's flat format (name / description / parameters at the
    top level alongside "type": "function"). The on-disk schema file stays in
    Chat Completions shape — this adapter runs at request time."""
    out: list[dict] = []
    for t in tools_chat_fmt:
        if t.get("type") != "function":
            out.append(t)
            continue
        fn = t.get("function", {})
        out.append({
            "type": "function",
            "name": fn.get("name"),
            "description": fn.get("description"),
            "parameters": fn.get("parameters", {}),
        })
    return out


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
        if path == "/api/tokens":
            return self.handle_tokens()
        self.send_error(404, "endpoint not found")

    def handle_tokens(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return self.json_response(400, {"error": "invalid Content-Length"})
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:  # noqa: BLE001
            return self.json_response(400, {"error": "invalid JSON body"})
        text = data.get("text", "")
        if not isinstance(text, str):
            return self.json_response(400, {"error": "'text' must be a string"})
        n, estimated = _count_tokens(text)
        return self.json_response(200, {
            "tokens": n,
            "encoding": "heuristic" if estimated else "o200k_base",
            "estimated": estimated,
            "chars": len(text),
        })

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
    # Uses the OpenAI Responses API (same as /api/rewrite). After iter 1,
    # subsequent iters chain via `previous_response_id` so only new
    # function_call_output items go up — instructions, tools, manifest, and
    # prior history all live on the OpenAI server keyed by response id.
    # Body: {"doc": "<full Markdown+ source>", "mode": "blocks"|"plain",
    #        "messages": [{role, content}, ...]}
    # Streams NDJSON with event types:
    #   {type:"start", model, tools_loaded, mode, manifest_blocks?}
    #   {type:"iteration", n}
    #   {type:"tool_call", id, name, args}
    #   {type:"tool_result", id, ok, result|error}
    #   {type:"delta", delta}           — assistant text (single chunk for now)
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
        # Cross-turn chain. Client passes back the response_id from the previous
        # `done` event; we forward it to OpenAI as previous_response_id so the
        # server reuses the stored instructions/manifest/prior-turn state and
        # we only have to upload the new user message. None → fresh chain.
        client_previous_response_id = (data.get("previous_response_id") or "").strip() or None
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

            # ===== Plain CLI baseline =====
            # No Markdown+ tools and no block manifest. The model gets one
            # low-level bash tool and must inspect document.md with ordinary
            # CLI commands, which is closer to a real "plain text in terminal"
            # workflow than custom read_lines/search functions.
            if mode == "plain":
                doc_lines = doc.splitlines()
                instructions = (
                    "You are answering questions about a Markdown document in "
                    "a plain CLI setting. The document has NOT been shown to "
                    "you inline. You have exactly one tool: bash(command). "
                    "The server runs your command in a temporary directory "
                    "containing document.md, also available as $DOC_PATH. "
                    "Use real bash text-inspection commands such as grep -n, "
                    "sed -n '120,180p' document.md, awk, head, tail, wc -l, "
                    "nl -ba document.md, or a small read-only python3 heredoc "
                    "that only reads document.md and prints findings. Do not "
                    "use Markdown+ block ids or mdp_* assumptions. Do not modify "
                    "files or access the network. Cite line numbers or command "
                    "evidence when useful."
                )
                # Build `input` based on whether we're chaining. With
                # previous_response_id, prior input/output items are part of
                # the threaded context, so only the latest user message needs
                # to be sent as input. Instructions are separate and are sent
                # on every request below so the current bash workflow remains
                # active on chained turns.
                if client_previous_response_id:
                    input_items = [{"role": "user", "content": history[-1]["content"]}]
                else:
                    input_items = [{"role": m["role"], "content": m["content"]} for m in history]

                write_ndjson({
                    "type": "start",
                    "model": MODEL,
                    "tools_loaded": 1,
                    "mode": "plain",
                    "total_lines": len(doc_lines),
                    "cli": "bash",
                    "chained": bool(client_previous_response_id),
                })

                previous_response_id: str | None = client_previous_response_id
                total_tool_calls = 0
                total_input_tokens = 0
                total_cached_tokens = 0
                total_output_tokens = 0
                for it in range(1, self.MAX_AGENT_ITERATIONS + 1):
                    write_ndjson({"type": "iteration", "n": it})
                    stream_kwargs: dict = {
                        "model": MODEL,
                        "tools": [_PLAIN_BASH_TOOL],
                        "parallel_tool_calls": False,
                        "input": input_items,
                        "instructions": instructions,
                    }
                    if previous_response_id is not None:
                        stream_kwargs["previous_response_id"] = previous_response_id

                    iter_text_chunks: list[str] = []
                    with client.responses.stream(**stream_kwargs) as stream:
                        for event in stream:
                            if getattr(event, "type", "") == "response.output_text.delta":
                                delta = getattr(event, "delta", "") or ""
                                if delta:
                                    iter_text_chunks.append(delta)
                                    write_ndjson({"type": "delta", "delta": delta})
                        final = stream.get_final_response()

                    in_tok, cached_tok, out_tok = _extract_usage(final)
                    total_input_tokens += in_tok
                    total_cached_tokens += cached_tok
                    total_output_tokens += out_tok
                    previous_response_id = final.id

                    pending_calls = [
                        item for item in (getattr(final, "output", None) or [])
                        if getattr(item, "type", "") == "function_call"
                    ]
                    if pending_calls:
                        next_input: list[dict] = []
                        for call in pending_calls:
                            total_tool_calls += 1
                            name = call.name
                            try:
                                args = json.loads(call.arguments or "{}")
                            except json.JSONDecodeError as e:
                                args = {"_parse_error": str(e), "_raw": call.arguments}
                            write_ndjson({
                                "type": "tool_call", "id": call.call_id,
                                "name": name, "args": args,
                            })
                            result = (
                                _execute_plain_bash(args, doc_path)
                                if name == "bash"
                                else {"error": f"unknown tool: {name}"}
                            )
                            is_err = isinstance(result, dict) and "error" in result
                            write_ndjson({
                                "type": "tool_result", "id": call.call_id,
                                "name": name, "ok": not is_err, "result": result,
                            })
                            next_input.append({
                                "type": "function_call_output",
                                "call_id": call.call_id,
                                "output": json.dumps(result, ensure_ascii=False, default=str),
                            })
                        input_items = next_input
                        continue

                    final_text = "".join(iter_text_chunks)
                    write_ndjson({
                        "type": "done",
                        "iterations": it,
                        "tool_calls": total_tool_calls,
                        "input_tokens": total_input_tokens,
                        "cached_tokens": total_cached_tokens,
                        "output_tokens": total_output_tokens,
                        "final_text_len": len(final_text),
                        "response_id": previous_response_id,
                    })
                    return

                write_ndjson({
                    "type": "error",
                    "error": f"stopped after {self.MAX_AGENT_ITERATIONS} CLI iterations without a final answer",
                })
                return

            # ===== Markdown+ tool-loop mode (default) =====
            # We do NOT preload the block manifest. On real docs the manifest
            # is ~50% of the document's tokens, and the Responses API reports
            # input_tokens cumulatively across iterations (prompt cache helps
            # by marking repeated prefixes as cached), so preloading it can
            # dominate a multi-iteration turn. Instead we let the LLM search
            # first; mdp_search_blocks returns body-context snippets that are
            # usually enough to answer without ever reading the full block, let
            # alone fetching the full manifest.
            tools_active = tools
            instructions = (
                "You are answering questions about a Markdown+ document the user uploaded. "
                "The document has NOT been shown to you. You have 7 mdp_* tools for "
                "progressive disclosure — use them in this order:\n"
                "  1. mdp_search_blocks(q=\"2-4 keywords from the question\") — START HERE. "
                "Returns matching blocks with body-context snippets, usually enough to answer directly.\n"
                "  2. mdp_list_blocks (optionally depth=2) — only if search returns nothing relevant, "
                "to see the document's block manifest and pick candidate ids by title/type.\n"
                "  3. mdp_read_block(id, children=true) — only when a snippet isn't enough and "
                "you need the full body of a specific block.\n"
                "  4. mdp_get_block_meta / mdp_list_children / mdp_resolve_xref / mdp_tree — "
                "for structural follow-ups (parent/child relationships, cross-references).\n"
                "Issue independent tool calls in parallel. Cite block ids in your answer "
                "(e.g. \"`#decision-canary` says ...\"). Keep answers concise unless asked otherwise."
            )
            responses_tools = _to_responses_tools(tools_active)
            # Build the iter-1 input. When we're chaining from a prior turn,
            # prior input/output items are already threaded through
            # previous_response_id, so the only new input item is this turn's
            # user message. Instructions are still sent on every request below.
            if client_previous_response_id:
                input_items: list[dict] = [
                    {"role": "user", "content": history[-1]["content"]}
                ]
            else:
                input_items = [
                    {"role": m["role"], "content": m["content"]} for m in history
                ]
            # Within-turn iteration chain — seeded from the cross-turn id so
            # iter 1 starts already chained when chaining; later iters chain
            # to their own previous iteration.
            previous_response_id: str | None = client_previous_response_id

            write_ndjson({
                "type": "start",
                "model": MODEL,
                "tools_loaded": len(tools_active),
                "mode": "blocks",
                "chained": bool(client_previous_response_id),
            })

            total_tool_calls = 0
            total_input_tokens = 0
            total_cached_tokens = 0
            total_output_tokens = 0
            final_text = ""
            for it in range(1, self.MAX_AGENT_ITERATIONS + 1):
                write_ndjson({"type": "iteration", "n": it})

                stream_kwargs: dict = {
                    "model": MODEL,
                    "tools": responses_tools,
                    "parallel_tool_calls": True,
                    "input": input_items,
                    "instructions": instructions,
                }
                if previous_response_id is not None:
                    # Chained — only the new items (latest user msg on a
                    # cross-turn chain, or function_call_output items on
                    # within-turn iter 2+) go up as input. Instructions and
                    # tool definitions are request parameters, so they are sent
                    # each time; prompt caching can mark repeated prefixes as
                    # cached in usage.
                    stream_kwargs["previous_response_id"] = previous_response_id

                # Stream the iteration. Text deltas (the final assistant answer
                # when the model decides it's done) are forwarded to the UI
                # token-by-token; function_calls are picked out of the final
                # response object after the stream closes.
                iter_text_chunks: list[str] = []
                with client.responses.stream(**stream_kwargs) as stream:
                    for event in stream:
                        if getattr(event, "type", "") == "response.output_text.delta":
                            delta = getattr(event, "delta", "") or ""
                            if delta:
                                iter_text_chunks.append(delta)
                                write_ndjson({"type": "delta", "delta": delta})
                    final = stream.get_final_response()

                in_tok, cached_tok, out_tok = _extract_usage(final)
                total_input_tokens += in_tok
                total_cached_tokens += cached_tok
                total_output_tokens += out_tok
                previous_response_id = final.id

                pending_calls = [
                    item for item in (getattr(final, "output", None) or [])
                    if getattr(item, "type", "") == "function_call"
                ]

                if pending_calls:
                    next_input: list[dict] = []
                    for call in pending_calls:
                        total_tool_calls += 1
                        name = call.name
                        try:
                            args = json.loads(call.arguments or "{}")
                        except json.JSONDecodeError as e:
                            args = {"_parse_error": str(e), "_raw": call.arguments}
                        write_ndjson({
                            "type": "tool_call", "id": call.call_id,
                            "name": name, "args": args,
                        })

                        result = _execute_mdp_tool(name, args, doc_path)
                        is_err = isinstance(result, dict) and "error" in result
                        write_ndjson({
                            "type": "tool_result", "id": call.call_id,
                            "name": name, "ok": not is_err, "result": result,
                        })
                        next_input.append({
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, ensure_ascii=False, default=str),
                        })
                    input_items = next_input
                    continue  # next iter sends just these outputs

                # No more tool calls — final text already streamed above. We
                # just need to emit the done event with usage totals + the
                # response_id so the client can chain the next turn.
                final_text = "".join(iter_text_chunks)
                write_ndjson({
                    "type": "done",
                    "iterations": it,
                    "tool_calls": total_tool_calls,
                    "input_tokens": total_input_tokens,
                    "cached_tokens": total_cached_tokens,
                    "output_tokens": total_output_tokens,
                    "final_text_len": len(final_text),
                    "response_id": previous_response_id,
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
