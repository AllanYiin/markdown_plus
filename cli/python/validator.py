"""
Markdown+ syntax validator.

Walks a Markdown+ document line-by-line, parses block headers, metadata, and
nesting, then runs the full output-contract rule set from the SKILL.

Usage:
    python markdown_plus_validator.py <path/to/doc.md>
    python markdown_plus_validator.py <path/to/doc.md> --json
    cat doc.md | python markdown_plus_validator.py -

Exit code 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# --- Controlled vocabularies (mirror metadata-vocabulary.md) ---

VALID_TYPES = {
    "document", "state", "history", "decision", "record", "issue", "note",
    "spec", "task", "reference", "figure", "table", "chart", "kpi", "card",
    "gauge", "targets", "dashboard", "dialogue", "turn", "step", "diagram",
}

VALID_STATUS = {
    "draft", "active", "proposed", "accepted", "rejected", "superseded",
    "deprecated", "archive", "healthy", "degraded", "down",
    "on-track", "behind", "exceeded", "done", "blocked", "open", "closed",
}

VALID_VISIBILITY = {"collapsed", "hidden"}
VALID_PRIORITY = {"critical", "high", "normal", "low"}
VALID_TREND = {"up", "up2", "down", "down2", "flat"}

ALLOWED_RAW_HTML_TAGS = {"br", "hr", "sub", "sup"}

# Types that REQUIRE a prose companion paragraph in the body
PROSE_REQUIRED_TYPES = {"figure", "table", "chart", "kpi", "gauge", "video", "audio"}

# Block header regex: bullet + space + **#id** + metadata inline codes
BLOCK_HEADER_RE = re.compile(
    r"^(?P<indent>\s*)- \*\*#(?P<id>[a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])\*\*"
    r"(?P<meta>(?:\s+`[^`]+`)*)\s*$"
)
META_PAIR_RE = re.compile(r"`([a-z][a-z0-9-]*):([^`]+)`")
CAPTION_RE = re.compile(r"^\s*\*([A-Z][a-zA-Z]+):\s+.+\*\s*$")
NUMBERED_CAPTION_RE = re.compile(r"^\s*\*([A-Z][a-zA-Z]+)\s+\d+:")
ID_KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


@dataclass
class Block:
    id: str
    type: str
    metadata: dict[str, str]
    indent: int  # number of leading spaces on the bullet line
    line: int  # 1-indexed
    body_lines: list[str] = field(default_factory=list)
    parent: str | None = None
    children: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str  # 'error' | 'warning'
    line: int
    code: str
    message: str
    block_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "block_id": self.block_id,
        }


# --- Parser ---

def parse_metadata_string(s: str) -> dict[str, str]:
    """Extract `key:value` pairs from inline-code metadata string."""
    return {m.group(1): m.group(2).strip() for m in META_PAIR_RE.finditer(s)}


def parse_blocks(text: str) -> tuple[list[Block], list[Issue]]:
    """Parse Markdown+ source into a flat block list. Indent encodes hierarchy."""
    lines = text.splitlines()
    blocks: list[Block] = []
    issues: list[Issue] = []
    current: Block | None = None
    in_fence = False
    fence_marker = ""

    for i, raw in enumerate(lines, 1):
        # Track code fences so we don't mis-parse `- **#...` inside code blocks
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            if current is not None:
                current.body_lines.append(raw)
            continue

        if in_fence:
            if current is not None:
                current.body_lines.append(raw)
            continue

        m = BLOCK_HEADER_RE.match(raw)
        if m:
            indent = len(m.group("indent"))
            block_id = m.group("id")
            meta_str = m.group("meta") or ""
            metadata = parse_metadata_string(meta_str)
            btype = metadata.get("type", "")
            current = Block(
                id=block_id,
                type=btype,
                metadata=metadata,
                indent=indent,
                line=i,
            )
            blocks.append(current)
        else:
            if current is not None:
                current.body_lines.append(raw)

    # Build parent/child links from indent
    stack: list[Block] = []
    for b in blocks:
        while stack and stack[-1].indent >= b.indent:
            stack.pop()
        if stack:
            b.parent = stack[-1].id
            stack[-1].children.append(b.id)
        stack.append(b)

    return blocks, issues


# --- Rules ---

def check_block(b: Block, ids_seen: set[str]) -> list[Issue]:
    issues: list[Issue] = []

    # R-ID-001: kebab-case
    if not ID_KEBAB_RE.match(b.id):
        issues.append(Issue("error", b.line, "ID-001",
                            f"block id {b.id!r} is not valid kebab-case", b.id))

    # R-ID-002: uniqueness
    if b.id in ids_seen:
        issues.append(Issue("error", b.line, "ID-002",
                            f"duplicate block id {b.id!r}", b.id))
    ids_seen.add(b.id)

    # R-TYPE-001: type required
    if not b.type:
        issues.append(Issue("error", b.line, "TYPE-001",
                            f"block {b.id!r} missing `type:` metadata", b.id))
    elif b.type not in VALID_TYPES and not b.type.startswith("x-"):
        issues.append(Issue("error", b.line, "TYPE-002",
                            f"block {b.id!r} has unknown type {b.type!r} (use closed vocabulary or 'x-' prefix)", b.id))

    # R-STATUS-001: valid status value
    status = b.metadata.get("status")
    if status and status not in VALID_STATUS:
        issues.append(Issue("warning", b.line, "STATUS-001",
                            f"block {b.id!r} has unknown status {status!r}", b.id))

    # R-VIS-001: valid visibility
    vis = b.metadata.get("visibility")
    if vis and vis not in VALID_VISIBILITY:
        issues.append(Issue("warning", b.line, "VIS-001",
                            f"block {b.id!r} has unknown visibility {vis!r}", b.id))

    # R-PRI-001: valid priority
    pri = b.metadata.get("priority")
    if pri and pri not in VALID_PRIORITY:
        issues.append(Issue("warning", b.line, "PRI-001",
                            f"block {b.id!r} has unknown priority {pri!r}", b.id))

    # R-UPD-001: updated must be ISO date
    upd = b.metadata.get("updated")
    if upd and upd != "unknown" and not re.match(r"^\d{4}-\d{2}-\d{2}$", upd):
        issues.append(Issue("warning", b.line, "UPD-001",
                            f"block {b.id!r} 'updated' {upd!r} is not ISO YYYY-MM-DD", b.id))

    # R-DEP-001: status:deprecated requires superseded-by
    if status in ("deprecated", "superseded"):
        if "superseded-by" not in b.metadata:
            issues.append(Issue("error", b.line, "DEP-001",
                                f"block {b.id!r} status:{status} requires 'superseded-by:'", b.id))

    # R-HIST-001: type:history should have visibility:collapsed
    if b.type == "history" and b.metadata.get("visibility") != "collapsed":
        issues.append(Issue("warning", b.line, "HIST-001",
                            f"block {b.id!r} type:history should have visibility:collapsed", b.id))

    # R-KPI-001: type:kpi must have value metadata
    if b.type == "kpi" and "value" not in b.metadata:
        issues.append(Issue("error", b.line, "KPI-001",
                            f"block {b.id!r} type:kpi missing 'value:' metadata", b.id))

    # R-GAUGE-001: type:gauge must have value/min/max/target/zones
    if b.type == "gauge":
        for required in ("value", "min", "max", "target", "zones"):
            if required not in b.metadata:
                issues.append(Issue("error", b.line, "GAUGE-001",
                                    f"block {b.id!r} type:gauge missing {required!r}", b.id))

    return issues


def check_global(blocks: list[Block], text: str) -> list[Issue]:
    issues: list[Issue] = []
    ids = {b.id for b in blocks}

    # R-XREF-001: superseded-by points to valid id
    for b in blocks:
        sb = b.metadata.get("superseded-by")
        if sb and sb not in ids:
            issues.append(Issue("error", b.line, "XREF-001",
                                f"block {b.id!r} superseded-by:{sb!r} not found", b.id))

        rel = b.metadata.get("related")
        if rel:
            for target in re.findall(r"[a-z0-9][a-z0-9-]*", rel):
                if target not in ids:
                    issues.append(Issue("warning", b.line, "XREF-002",
                                        f"block {b.id!r} related id {target!r} not found", b.id))

    # R-VARIANT-001: siblings with variant-group have distinct variant
    by_group: dict[tuple[str | None, str], list[Block]] = {}
    for b in blocks:
        vg = b.metadata.get("variant-group")
        if vg:
            by_group.setdefault((b.parent, vg), []).append(b)
    for (_, vg), siblings in by_group.items():
        variants = [b.metadata.get("variant") for b in siblings]
        if any(v is None for v in variants):
            issues.append(Issue("error", siblings[0].line, "VARIANT-001",
                                f"variant-group {vg!r} has sibling without 'variant:'"))
        if len(set(variants)) != len(variants):
            issues.append(Issue("error", siblings[0].line, "VARIANT-002",
                                f"variant-group {vg!r} has duplicate variant values"))

    # R-FENCE-001: no ::: directives outside code fences
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*:::", line):
            issues.append(Issue("error", i, "FENCE-001",
                                "':::' directive is not allowed in Markdown+"))

    # R-HTML-001: no raw HTML tags except allowed
    for i, line in enumerate(text.splitlines(), 1):
        # Skip code fences (rough — full skip handled by parser; this is a sanity sweep)
        for tag_match in re.finditer(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)\b", line):
            tag = tag_match.group(1).lower()
            if tag not in ALLOWED_RAW_HTML_TAGS and tag not in {"a", "code", "em", "strong"}:
                # Be lenient about inline tags <a>, <code>, <em>, <strong> which Markdown also produces
                # but flag the typical HTML wrappers.
                if tag in {"div", "span", "section", "article", "aside", "nav",
                           "header", "footer", "script", "style", "svg", "video",
                           "audio", "img", "table", "tr", "td", "th", "ul", "ol",
                           "li", "p", "h1", "h2", "h3", "h4", "h5", "h6",
                           "details", "summary", "figure", "figcaption"}:
                    issues.append(Issue("error", i, "HTML-001",
                                        f"raw HTML tag <{tag}> not allowed in Markdown+ source"))

    # R-BASE64-001: no inline base64
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"data:[a-z]+/[a-z+.-]+;base64,", line, re.IGNORECASE):
            issues.append(Issue("error", i, "BASE64-001",
                                "inline base64 / data URI not allowed (use relative file path)"))

    # R-SVG-INLINE-001: no inline <svg>
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"<\s*svg\b", line, re.IGNORECASE):
            issues.append(Issue("error", i, "SVG-001",
                                "inline <svg> not allowed (use ![alt](./path.svg))"))

    # R-PROSE-001: figure/table/chart/kpi/gauge blocks must have prose companion
    for b in blocks:
        if b.type in PROSE_REQUIRED_TYPES:
            # Find first non-blank, non-caption, non-code-fence, non-table line in body
            has_prose = False
            in_fence_body = False
            for line in b.body_lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("```") or s.startswith("~~~"):
                    in_fence_body = not in_fence_body
                    continue
                if in_fence_body:
                    continue
                if CAPTION_RE.match(line):
                    continue
                if s.startswith("|") or s.startswith("!["):
                    continue
                # found content — treat as prose if it has letters
                if re.search(r"[A-Za-z一-鿿]", s):
                    has_prose = True
                    break
            if not has_prose:
                issues.append(Issue("error", b.line, "PROSE-001",
                                    f"block {b.id!r} type:{b.type} missing prose companion paragraph", b.id))

    # R-CAP-NUM-001: caption must not contain hardcoded numbering
    for i, line in enumerate(text.splitlines(), 1):
        if NUMBERED_CAPTION_RE.match(line):
            issues.append(Issue("warning", i, "CAP-NUM-001",
                                "caption contains hardcoded number; viewer should auto-number"))

    # R-TBL-SIZE-001: tables with >30 rows should use data-source
    table_start_line = None
    table_rows = 0
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("|") and "|" in s[1:]:
            if table_start_line is None:
                table_start_line = i
            table_rows += 1
        else:
            if table_start_line is not None and table_rows > 30:
                issues.append(Issue("warning", table_start_line, "TBL-SIZE-001",
                                    f"table with {table_rows} rows should use 'data-source:./data/*.csv'"))
            table_start_line = None
            table_rows = 0

    return issues


def validate(text: str) -> tuple[list[Block], list[Issue]]:
    blocks, parse_issues = parse_blocks(text)
    issues = list(parse_issues)
    ids_seen: set[str] = set()
    for b in blocks:
        issues.extend(check_block(b, ids_seen))
    issues.extend(check_global(blocks, text))
    # sort by line
    issues.sort(key=lambda x: (x.line, x.code))
    return blocks, issues


# --- CLI ---

def format_human(blocks: list[Block], issues: list[Issue]) -> str:
    n_err = sum(1 for x in issues if x.severity == "error")
    n_warn = sum(1 for x in issues if x.severity == "warning")
    lines = [f"Markdown+ validator: {len(blocks)} blocks parsed; "
             f"{n_err} errors, {n_warn} warnings"]
    if not issues:
        lines.append("PASS")
        return "\n".join(lines)
    for x in issues:
        lines.append(f"  {x.severity.upper():<7} L{x.line:>4} [{x.code}] {x.message}")
    lines.append("PASS" if n_err == 0 else "FAIL")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args or args[0] == "-":
        text = sys.stdin.read()
        src_label = "<stdin>"
    else:
        path = Path(args[0])
        text = path.read_text(encoding="utf-8")
        src_label = str(path)

    blocks, issues = validate(text)

    if as_json:
        print(json.dumps({
            "source": src_label,
            "blocks": [
                {"id": b.id, "type": b.type, "parent": b.parent,
                 "children": b.children, "line": b.line, "metadata": b.metadata}
                for b in blocks
            ],
            "issues": [x.to_dict() for x in issues],
            "pass": all(x.severity != "error" for x in issues),
        }, ensure_ascii=False, indent=2))
    else:
        print(format_human(blocks, issues))

    return 0 if all(x.severity != "error" for x in issues) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
