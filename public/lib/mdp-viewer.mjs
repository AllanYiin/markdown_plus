// Markdown+ Viewer — ESM module, browser-ready.
// Renders Markdown+ source to an HTML string. Pair with viewer.css + viewer-runtime.js.
import { parseBlocks } from "../validator/mdp-validator.mjs";

const esc = (s) => String(s)
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
  .replaceAll('"',"&quot;").replaceAll("'","&#39;");

const CAPTION_RE = /^\s*\*([A-Z][a-zA-Z]+):\s+(.+?)\*\s*$/;
const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
const TABLE_SEP_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/;
const CODE_FENCE_RE = /^(\s*)(```|~~~)(\w*)\s*$/;
const GFM_ALERT_RE = /^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/;
const BLOCK_HEADER_PATTERN = /^\s*-\s+\*\*#[a-z0-9][a-z0-9-]*\*\*/;

function inlineMd(s) {
  let out = esc(s);
  // inline code (avoid touching its content)
  const parts = []; let last = 0;
  const re = /`([^`]+)`/g; let m;
  while ((m = re.exec(out)) !== null) {
    parts.push(out.slice(last, m.index));
    parts.push(`<code>${m[1]}</code>`);
    last = re.lastIndex;
  }
  parts.push(out.slice(last));
  out = parts.join("");
  out = out.replaceAll(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replaceAll(/(?<!\*)\*([^*\s][^*]*?)\*(?!\*)/g, "<em>$1</em>");
  out = out.replaceAll(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, a, b) => `<img src="${b}" alt="${a}" loading="lazy">`);
  out = out.replaceAll(/(?<!!)\[([^\]]+)\]\(([^)]+)\)/g, (_, a, b) => `<a href="${b}">${a}</a>`);
  return out;
}

function isSpecialLine(line) {
  const s = line.trim();
  return s.startsWith("```") || s.startsWith("~~~") || s.startsWith(">") ||
    s.startsWith("|") || s.startsWith("#") || s.startsWith("![") ||
    CAPTION_RE.test(line) || /^[-*]\s+/.test(s) || /^\d+\.\s+/.test(s);
}

function renderTable(rows, blockType) {
  const cells = (row) => {
    let body = row.trim();
    if (body.startsWith("|")) body = body.slice(1);
    if (body.endsWith("|")) body = body.slice(0, -1);
    return body.split("|").map(c => c.trim());
  };
  const renderCell = (c) => {
    const rg = c.match(/^\*\*—\s*(.+?)\s*—\*\*$/);
    if (rg) return `<td class="mdp-rowgroup" colspan="99"><span class="mdp-rowgroup-label">${esc(rg[1])}</span></td>`;
    const pill = c.match(/^`status:([a-z-]+)`$/);
    if (pill) return `<td><span class="mdp-pill mdp-pill-status-${pill[1]}">${esc(pill[1])}</span></td>`;
    const tr = c.match(/^`trend:(up2|down2|up|down|flat)`$/);
    if (tr) {
      const arrow = {up:"↑",up2:"↑↑",down:"↓",down2:"↓↓",flat:"→"}[tr[1]];
      return `<td><span class="mdp-trend mdp-trend-${tr[1]}">${arrow}</span></td>`;
    }
    return `<td>${inlineMd(c)}</td>`;
  };
  const header = cells(rows[0]);
  const bodyRows = rows.slice(2);
  const thead = `<thead><tr>${header.map(h => `<th>${inlineMd(h)}</th>`).join("")}</tr></thead>`;
  const trs = bodyRows.map(r => {
    const cs = cells(r);
    const isGroup = cs.some(c => /^\*\*—.*—\*\*$/.test(c));
    if (isGroup) {
      const labelCell = cs.find(c => /^\*\*—.*—\*\*$/.test(c));
      const label = labelCell.match(/^\*\*—\s*(.+?)\s*—\*\*$/)[1];
      return `<tr class="mdp-rowgroup-row"><td class="mdp-rowgroup" colspan="${header.length}"><span class="mdp-rowgroup-label">${esc(label)}</span></td></tr>`;
    }
    return `<tr>${cs.map(renderCell).join("")}</tr>`;
  }).join("");
  return `<table class="mdp-table mdp-table-${blockType}">${thead}<tbody>${trs}</tbody></table>`;
}

function renderBody(bodyLines, indent, blockType, captionCounters) {
  const base = indent + 2;
  const norm = bodyLines.map(line => {
    const head = line.slice(0, base);
    if (head.trim() === "") return line.slice(base);
    return line.replace(/^\s+/, "");
  });
  const out = [];
  let pendingCaption = null;
  let i = 0;
  const emitCaption = (kind, text) => {
    captionCounters[kind] = (captionCounters[kind] || 0) + 1;
    return `<figcaption class="mdp-caption mdp-caption-${kind.toLowerCase()}"><span class="mdp-caption-label">${esc(kind)} ${captionCounters[kind]}:</span> ${inlineMd(text)}</figcaption>`;
  };
  while (i < norm.length) {
    const line = norm[i];
    const s = line.trim();
    if (!s) { i++; continue; }

    const cm = line.match(CAPTION_RE);
    if (cm) { pendingCaption = { kind: cm[1], text: cm[2] }; i++; continue; }

    const fm = line.match(CODE_FENCE_RE);
    if (fm) {
      const lang = fm[3] || "";
      let j = i + 1;
      const codeLines = [];
      while (j < norm.length && !CODE_FENCE_RE.test(norm[j])) { codeLines.push(norm[j]); j++; }
      const codeText = codeLines.join("\n");
      let inner;
      if (lang.toLowerCase() === "mermaid") {
        inner = `<pre class="mermaid">${esc(codeText)}</pre>`;
      } else {
        const cls = lang ? ` class="language-${esc(lang)}"` : "";
        inner = `<pre class="mdp-code"><button class="mdp-copy" type="button" aria-label="Copy">Copy</button><code${cls}>${esc(codeText)}</code></pre>`;
      }
      if (pendingCaption) {
        out.push(`<figure class="mdp-fig mdp-fig-${pendingCaption.kind.toLowerCase()}">${inner}${emitCaption(pendingCaption.kind, pendingCaption.text)}</figure>`);
        pendingCaption = null;
      } else out.push(inner);
      i = j + 1;
      continue;
    }

    if (s.startsWith(">")) {
      let alertKind = null;
      const am = line.match(GFM_ALERT_RE);
      if (am) { alertKind = am[1].toLowerCase(); i++; }
      const ql = [];
      while (i < norm.length && (norm[i].trimStart().startsWith("> ") || norm[i].trim() === ">")) {
        ql.push(norm[i].trimStart().replace(/^>\s?/, ""));
        i++;
      }
      const inner = ql.join("\n").trim();
      if (alertKind) {
        out.push(`<aside class="mdp-callout mdp-callout-${alertKind}"><div class="mdp-callout-label">${alertKind.toUpperCase()}</div><div class="mdp-callout-body">${inlineMd(inner)}</div></aside>`);
      } else {
        out.push(`<blockquote>${inlineMd(inner)}</blockquote>`);
      }
      continue;
    }

    if (TABLE_ROW_RE.test(line)) {
      let j = i;
      const rows = [];
      while (j < norm.length && TABLE_ROW_RE.test(norm[j])) { rows.push(norm[j].trim()); j++; }
      if (rows.length >= 2 && TABLE_SEP_RE.test(rows[1])) {
        const tbl = renderTable(rows, blockType);
        if (pendingCaption) {
          out.push(`<figure class="mdp-fig mdp-fig-${pendingCaption.kind.toLowerCase()}">${emitCaption(pendingCaption.kind, pendingCaption.text)}${tbl}</figure>`);
          pendingCaption = null;
        } else out.push(tbl);
        i = j;
        continue;
      }
    }

    const imgM = line.match(/^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$/);
    if (imgM) {
      const img = `<img src="${imgM[2]}" alt="${imgM[1]}" loading="lazy">`;
      if (pendingCaption) {
        out.push(`<figure class="mdp-fig mdp-fig-${pendingCaption.kind.toLowerCase()}">${img}${emitCaption(pendingCaption.kind, pendingCaption.text)}</figure>`);
        pendingCaption = null;
      } else out.push(img);
      i++;
      continue;
    }

    const hm = s.match(/^(#{3,4})\s+(.+)$/);
    if (hm) { out.push(`<h${hm[1].length}>${inlineMd(hm[2])}</h${hm[1].length}>`); i++; continue; }

    if (/^[-*]\s+/.test(s)) {
      const items = [];
      while (i < norm.length && /^[-*]\s+/.test(norm[i].trim())) {
        items.push(norm[i].trim().slice(2));
        i++;
      }
      out.push("<ul>" + items.map(li => `<li>${inlineMd(li)}</li>`).join("") + "</ul>");
      continue;
    }

    if (/^\d+\.\s+/.test(s)) {
      const items = [];
      while (i < norm.length && /^\d+\.\s+/.test(norm[i].trim())) {
        items.push(norm[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      out.push("<ol>" + items.map(li => `<li>${inlineMd(li)}</li>`).join("") + "</ol>");
      continue;
    }

    const para = [s]; i++;
    while (i < norm.length && norm[i].trim() && !isSpecialLine(norm[i])) {
      para.push(norm[i].trim()); i++;
    }
    out.push(`<p>${inlineMd(para.join(" "))}</p>`);
  }
  return out.join("\n");
}

function renderKpi(b) {
  const m = b.metadata;
  const value = m.value || "";
  const unit = m.unit || "";
  const target = m.target || "";
  const delta = m.delta || "";
  const deltaCls = delta.startsWith("+") ? "positive" : delta.startsWith("-") ? "negative" : "neutral";
  let html = `<div class="mdp-kpi-head"><div class="mdp-kpi-metric">${esc(m.metric || "")}</div>`;
  html += `<div class="mdp-kpi-value">${esc(value)}${unit ? `<span class="mdp-kpi-unit">${esc(unit)}</span>` : ""}</div>`;
  if (target) html += `<div class="mdp-kpi-target">Target ${esc(target)}${esc(unit)}</div>`;
  if (delta) html += `<div class="mdp-kpi-delta mdp-kpi-delta-${deltaCls}">${esc(delta)}</div>`;
  html += `</div>`;
  return `<div class="mdp-kpi" data-status="${esc(m.status || "")}">${html}</div>`;
}

function renderGauge(b) {
  const m = b.metadata;
  const v = parseFloat(m.value || "0");
  const lo = parseFloat(m.min || "0");
  const hi = parseFloat(m.max || "100");
  const t = parseFloat(m.target || hi);
  const pct = hi === lo ? 0 : Math.max(0, Math.min(100, (v - lo) / (hi - lo) * 100));
  const tpct = hi === lo ? 0 : Math.max(0, Math.min(100, (t - lo) / (hi - lo) * 100));
  const zonesRaw = m.zones || "";
  const zones = [...zonesRaw.matchAll(/([\d.]+):([a-z]+)/g)].map(x => [parseFloat(x[1]), x[2]]);
  let gradient = "linear-gradient(to right, var(--mdp-zone-amber), var(--mdp-zone-green))";
  if (zones.length) {
    zones.sort((a, b) => a[0] - b[0]);
    const stops = [];
    let prev = 0;
    for (const [th, color] of zones) {
      const tp = Math.max(0, Math.min(100, (th - lo) / (hi - lo) * 100));
      stops.push(`var(--mdp-zone-${color}) ${prev}%`);
      stops.push(`var(--mdp-zone-${color}) ${tp}%`);
      prev = tp;
    }
    stops.push(`var(--mdp-zone-${zones[zones.length-1][1]}) 100%`);
    gradient = `linear-gradient(to right, ${stops.join(", ")})`;
  }
  const unit = esc(m.unit || "");
  return `<div class="mdp-gauge"><div class="mdp-gauge-track" style="background:${gradient}">`
    + `<div class="mdp-gauge-target" style="left:${tpct.toFixed(1)}%" title="Target ${t}${unit}"></div>`
    + `<div class="mdp-gauge-needle" style="left:${pct.toFixed(1)}%" title="Value ${v}${unit}"></div>`
    + `</div><div class="mdp-gauge-readout"><span class="mdp-gauge-value">${v}${unit}</span>`
    + ` <span class="mdp-gauge-target-text">/ target ${t}${unit}</span></div></div>`;
}

function renderBlockHeader(b, depth) {
  const title = b.metadata.title || b.id.replaceAll("-", " ");
  const status = b.metadata.status || "";
  const pill = status ? ` <span class="mdp-pill mdp-pill-status-${status}">${esc(status)}</span>` : "";
  const upd = b.metadata.updated ? ` <time class="mdp-updated">${esc(b.metadata.updated)}</time>` : "";
  const level = Math.min(2 + depth, 6);
  return `<header class="mdp-block-header"><h${level} class="mdp-block-title">`
    + `<a class="mdp-anchor" href="#${esc(b.id)}">#</a>${esc(title)}${pill}${upd}`
    + `<span class="mdp-type-badge">${esc(b.type)}</span></h${level}></header>`;
}

function renderBlock(b, byId, depth, captionCounters) {
  const isCollapsed = b.metadata.visibility === "collapsed" || b.type === "history";
  const tag = isCollapsed ? "details" : "section";
  let extras = "";
  if (b.type === "kpi") extras += renderKpi(b);
  if (b.type === "gauge") extras += renderGauge(b);
  const bodyHtml = renderBody(b.bodyLines, b.indent, b.type, captionCounters);

  let childrenBlock = "";
  if (b.children.length) {
    const groups = new Map();
    const order = [];
    for (const cid of b.children) {
      const cb = byId.get(cid);
      if (!cb) continue;
      const vg = cb.metadata["variant-group"];
      if (!groups.has(vg ?? null)) { groups.set(vg ?? null, []); order.push(vg ?? null); }
      groups.get(vg ?? null).push(cid);
    }
    const subParts = [];
    const nonVariant = b.children.filter(c => !byId.get(c)?.metadata["variant-group"]);
    if (nonVariant.length >= 3) {
      const items = nonVariant.map(cid => {
        const cb = byId.get(cid);
        const title = cb.metadata.title || cid.replaceAll("-", " ");
        return `<li><a href="#${esc(cid)}">${esc(title)}</a></li>`;
      }).join("");
      subParts.push(`<nav class="mdp-toc mdp-toc-inline" aria-label="目錄"><ul>${items}</ul></nav>`);
    }
    for (const vg of order) {
      const ids = groups.get(vg);
      if (vg === null) {
        for (const cid of ids) subParts.push(renderBlock(byId.get(cid), byId, depth + 1, captionCounters));
      } else {
        const btns = []; const panels = [];
        ids.forEach((cid, idx) => {
          const cb = byId.get(cid);
          const variant = cb.metadata.variant || "default";
          const active = idx === 0 ? " mdp-tab-active" : "";
          btns.push(`<button type="button" role="tab" class="mdp-tab-btn${active}" data-target="tab-${vg}-${variant}" aria-selected="${idx===0}">${esc(variant)}</button>`);
          panels.push(`<div role="tabpanel" id="tab-${vg}-${variant}" class="mdp-tab-panel${active}">${renderBlock(cb, byId, depth + 1, captionCounters)}</div>`);
        });
        subParts.push(`<div class="mdp-tabs" data-variant-group="${esc(vg)}"><div role="tablist" class="mdp-tab-list">${btns.join("")}</div><div class="mdp-tab-panels">${panels.join("")}</div></div>`);
      }
    }
    childrenBlock = `<div class="mdp-children">${subParts.join("")}</div>`;
  }

  let summaryHtml = "";
  if (isCollapsed) {
    const title = b.metadata.title || b.id.replaceAll("-", " ");
    summaryHtml = `<summary class="mdp-collapsed-summary"><span class="mdp-type-badge">${esc(b.type)}</span> ${esc(title)}</summary>`;
  }
  let classes = `mdp-block mdp-type-${b.type}`;
  if (b.metadata.accent) classes += ` mdp-accent-${b.metadata.accent}`;
  return `<${tag} id="${esc(b.id)}" class="${classes}" data-type="${esc(b.type)}">${summaryHtml}${isCollapsed ? "" : renderBlockHeader(b, depth)}${extras}<div class="mdp-body">${bodyHtml}</div>${childrenBlock}</${tag}>`;
}

function renderDashboardGrid(b, byId) {
  const kpis = b.children.map(c => byId.get(c)).filter(x => x && x.type === "kpi");
  if (!kpis.length) return "";
  const cards = kpis.map(cb => {
    const bodyHtml = renderBody(cb.bodyLines, cb.indent, cb.type, {});
    return `<div id="${esc(cb.id)}" class="mdp-kpi-card" data-status="${esc(cb.metadata.status || "")}">${renderKpi(cb)}<div class="mdp-body">${bodyHtml}</div></div>`;
  }).join("");
  return `<div class="mdp-dashboard-grid">${cards}</div>`;
}

export function renderDocument(text, opts = {}) {
  const blocks = parseBlocks(text);
  const byId = new Map(blocks.map(b => [b.id, b]));
  const top = blocks.filter(b => !b.parent);
  const lines = text.split(/\r?\n/);
  const h1Idx = lines.findIndex(l => l.startsWith("# "));
  const title = h1Idx >= 0 ? lines[h1Idx].slice(2).trim() : (opts.title || "Markdown+ Document");
  let intro = "";
  if (h1Idx >= 0) {
    const introLines = [];
    for (let j = h1Idx + 1; j < lines.length; j++) {
      if (BLOCK_HEADER_PATTERN.test(lines[j])) break;
      introLines.push(lines[j]);
    }
    const introText = introLines.join("\n").trim();
    if (introText) intro = `<p class="mdp-intro">${inlineMd(introText)}</p>`;
  }
  const tocSeen = new Set();
  const tocItems = top.flatMap(b => {
    const vg = b.metadata["variant-group"];
    if (vg) { if (tocSeen.has(vg)) return []; tocSeen.add(vg); }
    const t = b.metadata.title || b.id.replaceAll("-", " ");
    return `<li><a href="#${esc(b.id)}" data-toc-target="${esc(b.id)}">${esc(t)}</a></li>`;
  }).join("");
  const sidebar = top.length >= 3
    ? `<aside class="mdp-sidebar" aria-label="文件目錄"><div class="mdp-sidebar-title">目錄</div><ol class="mdp-toc">${tocItems}</ol></aside>`
    : "";

  const captionCounters = {};
  const renderedTop = [];
  const consumed = new Set();
  for (const b of top) {
    if (consumed.has(b.id)) continue;
    const vg = b.metadata["variant-group"];
    if (vg) {
      const siblings = top.filter(x => x.metadata["variant-group"] === vg);
      siblings.forEach(s => consumed.add(s.id));
      const btns = [], panels = [];
      siblings.forEach((s, idx) => {
        const variant = s.metadata.variant || "default";
        const active = idx === 0 ? " mdp-tab-active" : "";
        btns.push(`<button type="button" role="tab" class="mdp-tab-btn${active}" data-target="tab-${vg}-${variant}" aria-selected="${idx===0}">${esc(variant)}</button>`);
        panels.push(`<div role="tabpanel" id="tab-${vg}-${variant}" class="mdp-tab-panel${active}">${renderBlock(s, byId, 0, captionCounters)}</div>`);
      });
      renderedTop.push(`<div class="mdp-tabs" data-variant-group="${esc(vg)}"><div role="tablist" class="mdp-tab-list">${btns.join("")}</div><div class="mdp-tab-panels">${panels.join("")}</div></div>`);
      continue;
    }
    if (b.type === "dashboard") {
      const dashBody = renderBody(b.bodyLines, b.indent, b.type, captionCounters);
      const grid = renderDashboardGrid(b, byId);
      const others = b.children.map(c => byId.get(c)).filter(x => x && x.type !== "kpi")
        .map(c => renderBlock(c, byId, 1, captionCounters)).join("");
      renderedTop.push(`<section id="${esc(b.id)}" class="mdp-block mdp-type-dashboard" data-type="dashboard">${renderBlockHeader(b, 0)}<div class="mdp-body">${dashBody}</div>${grid}${others}</section>`);
      consumed.add(b.id);
      continue;
    }
    renderedTop.push(renderBlock(b, byId, 0, captionCounters));
    consumed.add(b.id);
  }

  return {
    title,
    intro,
    sidebarHtml: sidebar,
    mainHtml: renderedTop.join("\n"),
    blocks,
  };
}

// Convenience: full HTML doc string (used by Python wrapper / standalone)
export function renderFullDocument(text, opts = {}) {
  const r = renderDocument(text, opts);
  return `<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(r.title)}</title>${opts.cssHref ? `<link rel="stylesheet" href="${opts.cssHref}">` : ""}</head><body class="mdp-doc"><div class="mdp-layout">${r.sidebarHtml}<main class="mdp-main"><header class="mdp-doc-header"><h1>${esc(r.title)}</h1>${r.intro}</header>${r.mainHtml}</main></div>${opts.jsHref ? `<script src="${opts.jsHref}"></script>` : ""}</body></html>`;
}
