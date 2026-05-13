"""
Markdown+ → human-friendly HTML viewer.

Parses Markdown+, builds a block manifest, and emits a complete HTML5 document
with:
  - sticky scroll-spy sidebar TOC (when document has >= 3 children somewhere)
  - per-block <section> with status pills, updated-at, tags
  - <details> for type:history or visibility:collapsed
  - KPI cards (value/target/delta), gauges (value/min/max/zones)
  - actual-vs-target tables (progress bars, status pills)
  - dashboard grid layout
  - dialogue (chat-bubble layout)
  - variant tabs (siblings with same variant-group)
  - GFM alerts as colored callouts
  - Mermaid fences kept (client-side renders if mermaid.js is loaded)
  - auto-numbered captions (Table 1, Figure 1, ...)
  - code-copy buttons

Usage:
    python markdown_plus_viewer.py <doc.md> [--out <out.html>]
    cat doc.md | python markdown_plus_viewer.py - > out.html
"""
from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Reuse parser from validator
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validator"))
from markdown_plus_validator import Block, parse_blocks  # type: ignore

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


# --- Minimal inline markdown -> HTML (only what's needed inside a block body) ---

CODE_FENCE_RE = re.compile(r"^(\s*)(```|~~~)(\w*)\s*$")
GFM_ALERT_RE = re.compile(r"^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")
CAPTION_RE = re.compile(r"^\s*\*([A-Z][a-zA-Z]+):\s+(.+?)\*\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def inline_md(s: str) -> str:
    """Inline markdown: bold, italic, code, links, GFM auto-links."""
    s = html.escape(s)
    # inline code (do first so other patterns don't touch its contents)
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"`([^`]+)`", s):
        parts.append(s[last:m.start()])
        parts.append(f"<code>{m.group(1)}</code>")
        last = m.end()
    parts.append(s[last:])
    s = "".join(parts)
    # bold **x**
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    # italic *x*
    s = re.sub(r"(?<!\*)\*([^*\s][^*]*?)\*(?!\*)", r"<em>\1</em>", s)
    # images ![alt](src)
    s = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}" loading="lazy">',
        s,
    )
    # links [text](url)
    s = re.sub(
        r"(?<!!)\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        s,
    )
    return s


def render_body(body_lines: list[str], indent: int, block_type: str,
                caption_counters: dict[str, int]) -> str:
    """Render block body lines into HTML, stripping the block's base indent."""
    # Normalize indent: most body lines are indented `indent + 2`
    base = indent + 2
    norm: list[str] = []
    for line in body_lines:
        # strip up to `base` leading spaces but no more
        stripped = line[:base].lstrip(" ")
        if stripped == "":
            norm.append(line[base:] if len(line) >= base else line.lstrip(" "))
        else:
            norm.append(line.lstrip(" "))
    out: list[str] = []
    i = 0
    n = len(norm)
    pending_caption: tuple[str, str] | None = None  # (kind, text)

    def emit_caption(kind: str, text: str) -> str:
        caption_counters[kind] = caption_counters.get(kind, 0) + 1
        num = caption_counters[kind]
        return f'<figcaption class="mdp-caption mdp-caption-{kind.lower()}"><span class="mdp-caption-label">{kind} {num}:</span> {inline_md(text)}</figcaption>'

    while i < n:
        line = norm[i]
        stripped = line.strip()

        # Blank line
        if not stripped:
            i += 1
            continue

        # Caption
        cm = CAPTION_RE.match(line)
        if cm:
            pending_caption = (cm.group(1), cm.group(2))
            i += 1
            continue

        # Code fence
        fm = CODE_FENCE_RE.match(line)
        if fm:
            lang = fm.group(3) or ""
            j = i + 1
            code_lines: list[str] = []
            while j < n and not CODE_FENCE_RE.match(norm[j]):
                code_lines.append(norm[j])
                j += 1
            code_text = "\n".join(code_lines)
            if lang.lower() == "mermaid":
                # Keep as <pre class="mermaid"> so mermaid.js (if loaded) renders it.
                fig_inner = f'<pre class="mermaid">{html.escape(code_text)}</pre>'
            else:
                lang_cls = f' class="language-{html.escape(lang)}"' if lang else ""
                fig_inner = (
                    f'<pre class="mdp-code"><button class="mdp-copy" type="button" '
                    f'aria-label="Copy code">Copy</button>'
                    f'<code{lang_cls}>{html.escape(code_text)}</code></pre>'
                )
            if pending_caption:
                kind, text = pending_caption
                out.append(f'<figure class="mdp-fig mdp-fig-{kind.lower()}">{fig_inner}{emit_caption(kind, text)}</figure>')
                pending_caption = None
            else:
                out.append(fig_inner)
            i = j + 1
            continue

        # GFM alert blockquote
        if line.lstrip().startswith("> ") or line.lstrip() == ">":
            alert_kind = None
            alert_first = i
            am = GFM_ALERT_RE.match(line)
            if am:
                alert_kind = am.group(1).lower()
                i += 1
            quote_lines: list[str] = []
            while i < n and (norm[i].lstrip().startswith("> ") or norm[i].lstrip() == ">"):
                quote_lines.append(norm[i].lstrip()[1:].lstrip())
                i += 1
            inner = "\n".join(quote_lines).strip()
            if alert_kind:
                out.append(
                    f'<aside class="mdp-callout mdp-callout-{alert_kind}">'
                    f'<div class="mdp-callout-label">{alert_kind.upper()}</div>'
                    f'<div class="mdp-callout-body">{inline_md(inner)}</div></aside>'
                )
            else:
                out.append(f"<blockquote>{inline_md(inner)}</blockquote>")
            continue

        # Table
        if TABLE_ROW_RE.match(line):
            j = i
            rows: list[str] = []
            while j < n and TABLE_ROW_RE.match(norm[j]):
                rows.append(norm[j].strip())
                j += 1
            if len(rows) >= 2 and TABLE_SEP_RE.match(rows[1]):
                table_html = _render_table(rows, block_type)
                if pending_caption:
                    kind, text = pending_caption
                    out.append(f'<figure class="mdp-fig mdp-fig-{kind.lower()}">{emit_caption(kind, text)}{table_html}</figure>')
                    pending_caption = None
                else:
                    out.append(table_html)
                i = j
                continue

        # Image-only line
        img_match = re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if img_match:
            alt, src = img_match.group(1), img_match.group(2)
            img_html = f'<img src="{src}" alt="{alt}" loading="lazy">'
            if pending_caption:
                kind, text = pending_caption
                out.append(f'<figure class="mdp-fig mdp-fig-{kind.lower()}">{img_html}{emit_caption(kind, text)}</figure>')
                pending_caption = None
            else:
                out.append(img_html)
            i += 1
            continue

        # H3 / H4 inside block body
        h_match = re.match(r"^(#{3,4})\s+(.+)$", stripped)
        if h_match:
            level = len(h_match.group(1))
            out.append(f"<h{level}>{inline_md(h_match.group(2))}</h{level}>")
            i += 1
            continue

        # Bullet list (non-block)
        if re.match(r"^[-*]\s+", stripped):
            list_items: list[str] = []
            while i < n and re.match(r"^[-*]\s+", norm[i].strip()):
                list_items.append(norm[i].strip()[2:])
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline_md(li)}</li>" for li in list_items) + "</ul>")
            continue

        # Numbered list
        if re.match(r"^\d+\.\s+", stripped):
            list_items: list[str] = []
            while i < n and re.match(r"^\d+\.\s+", norm[i].strip()):
                list_items.append(re.sub(r"^\d+\.\s+", "", norm[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline_md(li)}</li>" for li in list_items) + "</ol>")
            continue

        # Paragraph
        para_lines: list[str] = [stripped]
        i += 1
        while i < n and norm[i].strip() and not _is_special(norm[i]):
            para_lines.append(norm[i].strip())
            i += 1
        out.append(f"<p>{inline_md(' '.join(para_lines))}</p>")

    return "\n".join(out)


def _is_special(line: str) -> bool:
    s = line.strip()
    return (
        s.startswith("```") or s.startswith("~~~") or s.startswith(">") or
        s.startswith("|") or s.startswith("#") or s.startswith("![") or
        CAPTION_RE.match(line) is not None or
        re.match(r"^[-*]\s+", s) is not None or
        re.match(r"^\d+\.\s+", s) is not None
    )


def _render_table(rows: list[str], block_type: str) -> str:
    """Render a markdown table. Cell-level `key:value` inline codes become pills."""
    def cells(row: str) -> list[str]:
        body = row.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|"):
            body = body[:-1]
        return [c.strip() for c in body.split("|")]

    def render_cell(cell: str) -> str:
        # Detect row-group cells: **— xxx —**
        rg = re.match(r"^\*\*—\s*(.+?)\s*—\*\*$", cell)
        if rg:
            return f'<td class="mdp-rowgroup" colspan="99"><span class="mdp-rowgroup-label">{html.escape(rg.group(1))}</span></td>'
        # Detect status: pill
        pill = re.match(r"^`status:([a-z-]+)`$", cell)
        if pill:
            v = pill.group(1)
            return f'<td><span class="mdp-pill mdp-pill-status-{v}">{html.escape(v)}</span></td>'
        # Trend arrow
        trend = re.match(r"^`trend:(up2|down2|up|down|flat)`$", cell)
        if trend:
            v = trend.group(1)
            arrow = {"up": "↑", "up2": "↑↑", "down": "↓", "down2": "↓↓", "flat": "→"}[v]
            return f'<td><span class="mdp-trend mdp-trend-{v}">{arrow}</span></td>'
        return f"<td>{inline_md(cell)}</td>"

    header = cells(rows[0])
    # rows[1] is separator
    body_rows = rows[2:]
    thead = "<thead><tr>" + "".join(f"<th>{inline_md(h)}</th>" for h in header) + "</tr></thead>"

    body_html_rows: list[str] = []
    for r in body_rows:
        cs = cells(r)
        # row-group detection: any cell is **— xxx —**
        is_group = any(re.match(r"^\*\*—.*—\*\*$", c) for c in cs)
        if is_group:
            label_cell = next(c for c in cs if re.match(r"^\*\*—.*—\*\*$", c))
            label = re.match(r"^\*\*—\s*(.+?)\s*—\*\*$", label_cell).group(1)
            body_html_rows.append(
                f'<tr class="mdp-rowgroup-row"><td class="mdp-rowgroup" colspan="{len(header)}">'
                f'<span class="mdp-rowgroup-label">{html.escape(label)}</span></td></tr>'
            )
        else:
            body_html_rows.append("<tr>" + "".join(render_cell(c) for c in cs) + "</tr>")

    return (
        f'<table class="mdp-table mdp-table-{block_type}">'
        f'{thead}<tbody>{"".join(body_html_rows)}</tbody></table>'
    )


# --- Block-level rendering ---

@dataclass
class RenderedBlock:
    block: Block
    html: str
    children_html: str = ""


def render_kpi(b: Block) -> str:
    metric = b.metadata.get("metric", "")
    value = b.metadata.get("value", "")
    unit = b.metadata.get("unit", "")
    target = b.metadata.get("target", "")
    delta = b.metadata.get("delta", "")
    status = b.metadata.get("status", "")
    delta_cls = "neutral"
    if delta.startswith("+"):
        delta_cls = "positive"
    elif delta.startswith("-"):
        delta_cls = "negative"
    parts = [
        f'<div class="mdp-kpi-metric">{html.escape(metric)}</div>',
        f'<div class="mdp-kpi-value">{html.escape(value)}{f"<span class=mdp-kpi-unit>{html.escape(unit)}</span>" if unit else ""}</div>',
    ]
    if target:
        parts.append(f'<div class="mdp-kpi-target">Target {html.escape(target)}{html.escape(unit)}</div>')
    if delta:
        parts.append(f'<div class="mdp-kpi-delta mdp-kpi-delta-{delta_cls}">{html.escape(delta)}</div>')
    head = f'<div class="mdp-kpi-head">{"".join(parts)}</div>'
    status_attr = f' data-status="{status}"' if status else ""
    return f'<div class="mdp-kpi"{status_attr}>{head}</div>'


def render_gauge(b: Block) -> str:
    try:
        value = float(b.metadata.get("value", "0"))
        gmin = float(b.metadata.get("min", "0"))
        gmax = float(b.metadata.get("max", "100"))
        target = float(b.metadata.get("target", gmax))
    except ValueError:
        value, gmin, gmax, target = 0, 0, 100, 100
    zones_raw = b.metadata.get("zones", "")
    # zones like "[99.0:red,99.9:amber,99.95:green]"
    zones = []
    for m in re.finditer(r"([\d.]+):([a-z]+)", zones_raw):
        zones.append((float(m.group(1)), m.group(2)))
    pct = 0 if gmax == gmin else max(0, min(100, (value - gmin) / (gmax - gmin) * 100))
    target_pct = 0 if gmax == gmin else max(0, min(100, (target - gmin) / (gmax - gmin) * 100))
    # Build gradient
    if zones:
        sorted_zones = sorted(zones)
        stops = []
        prev_pct = 0
        for threshold, color in sorted_zones:
            tp = max(0, min(100, (threshold - gmin) / (gmax - gmin) * 100))
            stops.append(f"var(--mdp-zone-{color}) {prev_pct}%")
            stops.append(f"var(--mdp-zone-{color}) {tp}%")
            prev_pct = tp
        stops.append(f"var(--mdp-zone-{sorted_zones[-1][1]}) 100%")
        gradient = f"linear-gradient(to right, {', '.join(stops)})"
    else:
        gradient = "linear-gradient(to right, var(--mdp-zone-amber), var(--mdp-zone-green))"
    unit = b.metadata.get("unit", "")
    return (
        f'<div class="mdp-gauge">'
        f'<div class="mdp-gauge-track" style="background:{gradient}">'
        f'<div class="mdp-gauge-target" style="left:{target_pct:.1f}%" title="Target {target}{unit}"></div>'
        f'<div class="mdp-gauge-needle" style="left:{pct:.1f}%" title="Value {value}{unit}"></div>'
        f'</div>'
        f'<div class="mdp-gauge-readout"><span class="mdp-gauge-value">{value}{html.escape(unit)}</span>'
        f' <span class="mdp-gauge-target-text">/ target {target}{html.escape(unit)}</span></div>'
        f'</div>'
    )


def render_block_header(b: Block, depth: int) -> str:
    title_text = b.metadata.get("title", b.id.replace("-", " "))
    # status pill
    status = b.metadata.get("status", "")
    pill = f' <span class="mdp-pill mdp-pill-status-{status}">{html.escape(status)}</span>' if status else ""
    updated = b.metadata.get("updated", "")
    upd = f' <time class="mdp-updated">{html.escape(updated)}</time>' if updated else ""
    h_level = min(2 + depth, 6)
    anchor = f'<a class="mdp-anchor" href="#{html.escape(b.id)}">#</a>'
    type_badge = f'<span class="mdp-type-badge">{html.escape(b.type)}</span>'
    return (
        f'<header class="mdp-block-header">'
        f'<h{h_level} class="mdp-block-title">{anchor}{html.escape(title_text)}{pill}{upd}{type_badge}</h{h_level}>'
        f"</header>"
    )


def render_block(b: Block, by_id: dict[str, Block], depth: int,
                 caption_counters: dict[str, int]) -> str:
    """Render a single block + recursively its children."""
    is_collapsed = b.metadata.get("visibility") == "collapsed" or b.type == "history"
    tag = "details" if is_collapsed else "section"
    extras: list[str] = []

    if b.type == "kpi":
        extras.append(render_kpi(b))
    if b.type == "gauge":
        extras.append(render_gauge(b))

    body_html = render_body(b.body_lines, b.indent, b.type, caption_counters)

    # Render children
    children_block = ""
    if b.children:
        # variant grouping: if siblings share variant-group, render as tab set
        # group children by variant-group key
        groups: dict[str | None, list[str]] = {}
        order: list[str | None] = []
        for cid in b.children:
            cb = by_id.get(cid)
            if cb is None:
                continue
            vg = cb.metadata.get("variant-group")
            if vg not in groups:
                groups[vg] = []
                order.append(vg)
            groups[vg].append(cid)

        sub_parts: list[str] = []
        # Auto-TOC for non-variant children if >= 3
        non_variant_children = [c for c in b.children if not by_id[c].metadata.get("variant-group")]
        if len(non_variant_children) >= 3:
            toc_items = []
            for cid in non_variant_children:
                cb = by_id[cid]
                title = cb.metadata.get("title", cid.replace("-", " "))
                toc_items.append(f'<li><a href="#{html.escape(cid)}">{html.escape(title)}</a></li>')
            sub_parts.append(f'<nav class="mdp-toc mdp-toc-inline" aria-label="目錄"><ul>{"".join(toc_items)}</ul></nav>')

        for vg in order:
            ids = groups[vg]
            if vg is None:
                for cid in ids:
                    cb = by_id[cid]
                    sub_parts.append(render_block(cb, by_id, depth + 1, caption_counters))
            else:
                # Build a tab set
                tab_btns = []
                tab_panels = []
                for idx, cid in enumerate(ids):
                    cb = by_id[cid]
                    variant = cb.metadata.get("variant", "default")
                    active = " mdp-tab-active" if idx == 0 else ""
                    tab_btns.append(
                        f'<button type="button" role="tab" class="mdp-tab-btn{active}" '
                        f'data-target="tab-{vg}-{variant}" aria-selected="{str(idx == 0).lower()}">'
                        f'{html.escape(variant)}</button>'
                    )
                    tab_panels.append(
                        f'<div role="tabpanel" id="tab-{vg}-{variant}" '
                        f'class="mdp-tab-panel{active}">'
                        f"{render_block(cb, by_id, depth + 1, caption_counters)}"
                        f"</div>"
                    )
                sub_parts.append(
                    f'<div class="mdp-tabs" data-variant-group="{html.escape(vg)}">'
                    f'<div role="tablist" class="mdp-tab-list">{"".join(tab_btns)}</div>'
                    f'<div class="mdp-tab-panels">{"".join(tab_panels)}</div>'
                    f"</div>"
                )
        children_block = "<div class=\"mdp-children\">" + "".join(sub_parts) + "</div>"

    summary_html = ""
    if is_collapsed:
        title_text = b.metadata.get("title", b.id.replace("-", " "))
        summary_html = (
            f'<summary class="mdp-collapsed-summary">'
            f'<span class="mdp-type-badge">{html.escape(b.type)}</span> '
            f'{html.escape(title_text)}'
            f"</summary>"
        )
    classes = f"mdp-block mdp-type-{b.type}"
    if b.metadata.get("accent"):
        classes += f" mdp-accent-{b.metadata['accent']}"
    return (
        f'<{tag} id="{html.escape(b.id)}" class="{classes}" data-type="{b.type}">'
        f"{summary_html}"
        f"{'' if is_collapsed else render_block_header(b, depth)}"
        f"{''.join(extras)}"
        f'<div class="mdp-body">{body_html}</div>'
        f"{children_block}"
        f"</{tag}>"
    )


def render_dashboard_children(b: Block, by_id: dict[str, Block]) -> str:
    """Special grid layout for type:dashboard: render KPI children as grid cards."""
    parts = []
    for cid in b.children:
        cb = by_id.get(cid)
        if cb is None:
            continue
        body_html = render_body(cb.body_lines, cb.indent, cb.type, {})
        parts.append(
            f'<div id="{html.escape(cb.id)}" class="mdp-kpi-card" data-status="{cb.metadata.get("status","")}">'
            f'{render_kpi(cb) if cb.type == "kpi" else ""}'
            f'<div class="mdp-body">{body_html}</div>'
            f'</div>'
        )
    return f'<div class="mdp-dashboard-grid">{"".join(parts)}</div>'


def render_document(text: str, title: str = "Markdown+ Document",
                    embed_assets: bool = True) -> str:
    blocks, _ = parse_blocks(text)
    by_id: dict[str, Block] = {b.id: b for b in blocks}
    top_level = [b for b in blocks if b.parent is None]

    # H1 from first H1 line if present
    h1_match = re.search(r"^#\s+(.+?)$", text, re.MULTILINE)
    if h1_match:
        title = h1_match.group(1).strip()

    # Intro paragraph (text between H1 and first block)
    intro = ""
    lines = text.splitlines()
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1)
    if h1_idx >= 0:
        intro_lines = []
        for j in range(h1_idx + 1, len(lines)):
            ll = lines[j]
            if BLOCK_HEADER_PATTERN.match(ll):
                break
            intro_lines.append(ll)
        intro_text = "\n".join(intro_lines).strip()
        if intro_text:
            intro = f'<p class="mdp-intro">{inline_md(intro_text)}</p>'

    # Sidebar TOC: all top-level blocks (skip variant siblings)
    toc_seen_vg: set[str] = set()
    toc_items = []
    for b in top_level:
        vg = b.metadata.get("variant-group")
        if vg:
            if vg in toc_seen_vg:
                continue
            toc_seen_vg.add(vg)
        title_text = b.metadata.get("title", b.id.replace("-", " "))
        toc_items.append(
            f'<li><a href="#{html.escape(b.id)}" data-toc-target="{html.escape(b.id)}">'
            f'{html.escape(title_text)}</a></li>'
        )
    sidebar = (
        f'<aside class="mdp-sidebar" aria-label="文件目錄">'
        f'<div class="mdp-sidebar-title">目錄</div>'
        f'<ol class="mdp-toc">{"".join(toc_items)}</ol>'
        f"</aside>"
        if len(top_level) >= 3
        else ""
    )

    # Render top-level blocks
    caption_counters: dict[str, int] = {}
    rendered_top: list[str] = []
    consumed: set[str] = set()
    for b in top_level:
        if b.id in consumed:
            continue
        vg = b.metadata.get("variant-group")
        if vg:
            # Collect all top-level siblings with same variant-group
            siblings = [x for x in top_level if x.metadata.get("variant-group") == vg]
            for s in siblings:
                consumed.add(s.id)
            tab_btns = []
            tab_panels = []
            for idx, s in enumerate(siblings):
                variant = s.metadata.get("variant", "default")
                active = " mdp-tab-active" if idx == 0 else ""
                tab_btns.append(
                    f'<button type="button" role="tab" class="mdp-tab-btn{active}" '
                    f'data-target="tab-{vg}-{variant}" aria-selected="{str(idx == 0).lower()}">'
                    f'{html.escape(variant)}</button>'
                )
                tab_panels.append(
                    f'<div role="tabpanel" id="tab-{vg}-{variant}" class="mdp-tab-panel{active}">'
                    f'{render_block(s, by_id, 0, caption_counters)}'
                    f'</div>'
                )
            rendered_top.append(
                f'<div class="mdp-tabs" data-variant-group="{html.escape(vg)}">'
                f'<div role="tablist" class="mdp-tab-list">{"".join(tab_btns)}</div>'
                f'<div class="mdp-tab-panels">{"".join(tab_panels)}</div>'
                f"</div>"
            )
            continue

        # Dashboard special handling: KPI children become grid
        if b.type == "dashboard":
            dash_body = render_body(b.body_lines, b.indent, b.type, caption_counters)
            kpi_children = [by_id[c] for c in b.children if by_id[c].type == "kpi"]
            other_children = [by_id[c] for c in b.children if by_id[c].type != "kpi"]
            grid = render_dashboard_children(
                Block(id=b.id + "_grid", type="dashboard", metadata={}, indent=0, line=0,
                      children=[c.id for c in kpi_children]),
                by_id,
            ) if kpi_children else ""
            others = "".join(render_block(c, by_id, 1, caption_counters) for c in other_children)
            rendered_top.append(
                f'<section id="{html.escape(b.id)}" class="mdp-block mdp-type-dashboard" data-type="dashboard">'
                f'{render_block_header(b, 0)}'
                f'<div class="mdp-body">{dash_body}</div>'
                f'{grid}{others}'
                f"</section>"
            )
            consumed.add(b.id)
            continue

        rendered_top.append(render_block(b, by_id, 0, caption_counters))
        consumed.add(b.id)

    main_html = "\n".join(rendered_top)

    css = (ASSETS_DIR / "viewer.css").read_text(encoding="utf-8") if embed_assets and (ASSETS_DIR / "viewer.css").exists() else ""
    js = (ASSETS_DIR / "viewer-runtime.js").read_text(encoding="utf-8") if embed_assets and (ASSETS_DIR / "viewer-runtime.js").exists() else ""

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{css}</style>
</head>
<body class="mdp-doc">
<div class="mdp-layout">
{sidebar}
<main class="mdp-main">
<header class="mdp-doc-header"><h1>{html.escape(title)}</h1>{intro}</header>
{main_html}
</main>
</div>
<script>{js}</script>
</body>
</html>"""


# Block header pattern (mirrors validator)
BLOCK_HEADER_PATTERN = re.compile(r"^\s*-\s+\*\*#[a-z0-9][a-z0-9-]*\*\*")


# --- CLI ---

def main(argv: list[str]) -> int:
    args = argv[1:]
    out_path = None
    if "--out" in args:
        idx = args.index("--out")
        out_path = args[idx + 1]
        args = args[:idx] + args[idx + 2:]
    embed = "--no-embed" not in args
    args = [a for a in args if a != "--no-embed"]

    if not args or args[0] == "-":
        text = sys.stdin.read()
        title = "Markdown+ Document"
    else:
        p = Path(args[0])
        text = p.read_text(encoding="utf-8")
        title = p.stem

    html_out = render_document(text, title=title, embed_assets=embed)

    if out_path:
        Path(out_path).write_text(html_out, encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)
    else:
        sys.stdout.write(html_out)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
