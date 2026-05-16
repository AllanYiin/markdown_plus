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
const SVG_INLINE_LIMIT_BYTES = 16 * 1024;
const KEYWORD_SENTENCE_SPLIT_RE = /[\s　，。!?！？；：、,.;:()\[\]【】「」『』""''《》<>\/\\\n\r\t]+/;

function isCJK(ch) {
  if (!ch) return false;
  const c = ch.codePointAt(0);
  return (c >= 0x4e00 && c <= 0x9fff) || (c >= 0x3400 && c <= 0x4dbf) || (c >= 0xf900 && c <= 0xfaff);
}

function entropyOfMap(map) {
  let total = 0;
  for (const v of map.values()) total += v;
  if (total === 0) return 0;
  let ent = 0;
  for (const v of map.values()) {
    const p = v / total;
    ent -= p * Math.log(p);
  }
  return ent;
}

// Dictionary-free keyword extractor — N-gram (CJK 2–8) + ASCII tokens, scored by
// PMI cohesion × min(left, right) Shannon entropy. Based on "無詞典新詞發現" method.
export class KeywordExtractor {
  constructor(opts) {
    opts = opts || {};
    this.minLen = opts.minLen != null ? opts.minLen : 2;
    this.maxLen = opts.maxLen != null ? opts.maxLen : 8;
    this.minFreq = opts.minFreq != null ? opts.minFreq : 2;
    this.minPmi = opts.minPmi != null ? opts.minPmi : 1.0;
    this.minEntropy = opts.minEntropy != null ? opts.minEntropy : 0.4;
    this.minAsciiLen = opts.minAsciiLen != null ? opts.minAsciiLen : 3;
    this.ngramFreq = new Map();
    this.leftNeighbors = new Map();
    this.rightNeighbors = new Map();
    this.totalChars = 0;
  }
  _inc(k) { this.ngramFreq.set(k, (this.ngramFreq.get(k) || 0) + 1); }
  _addNeighbor(cand, left, right) {
    let lm = this.leftNeighbors.get(cand);
    if (!lm) { lm = new Map(); this.leftNeighbors.set(cand, lm); }
    let rm = this.rightNeighbors.get(cand);
    if (!rm) { rm = new Map(); this.rightNeighbors.set(cand, rm); }
    lm.set(left, (lm.get(left) || 0) + 1);
    rm.set(right, (rm.get(right) || 0) + 1);
  }
  static cleanText(text) {
    return String(text)
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/~~~[\s\S]*?~~~/g, " ")
      .replace(/`[^`]*`/g, " ")
      .replace(/!\[[^\]]*\]\([^)]+\)/g, " ")
      .replace(/\[[^\]]+\]\([^)]+\)/g, " ")
      .replace(/^\s*-\s+\*\*#[a-z0-9][a-z0-9-]*\*\*.*$/gm, " ")
      .replace(/^\s*#{1,6}\s+/gm, " ")
      .replace(/[*_>|]+/g, " ");
  }
  fit(text) {
    const cleaned = KeywordExtractor.cleanText(text);
    const sentences = cleaned.split(KEYWORD_SENTENCE_SPLIT_RE).filter(s => s.length >= 2);
    for (const sent of sentences) this._scanSentence(sent);
    return this;
  }
  _scanSentence(sent) {
    const arr = Array.from(sent);
    const n = arr.length;
    for (let i = 0; i < n; i++) {
      if (isCJK(arr[i])) this._inc(arr[i]);
      this.totalChars++;
    }
    for (let i = 0; i < n; i++) {
      if (!isCJK(arr[i])) continue;
      for (let L = this.minLen; L <= this.maxLen && i + L <= n; L++) {
        let ok = true;
        for (let k = 0; k < L; k++) {
          if (!isCJK(arr[i + k])) { ok = false; break; }
        }
        if (!ok) break;
        const cand = arr.slice(i, i + L).join("");
        this._inc(cand);
        const left = i > 0 ? arr[i - 1] : "<BOS>";
        const right = i + L < n ? arr[i + L] : "<EOS>";
        this._addNeighbor(cand, left, right);
      }
    }
    const tokenRe = /[A-Za-z][A-Za-z0-9+\-]*/g;
    let m;
    while ((m = tokenRe.exec(sent)) !== null) {
      const tok = m[0];
      if (tok.length < this.minAsciiLen) continue;
      this._inc(tok);
      const startIdx = m.index;
      const endIdx = m.index + tok.length;
      const left = startIdx > 0 ? sent[startIdx - 1] : "<BOS>";
      const right = endIdx < sent.length ? sent[endIdx] : "<EOS>";
      this._addNeighbor(tok, left, right);
    }
  }
  _prob(token) { return (this.ngramFreq.get(token) || 0) / Math.max(this.totalChars, 1); }
  cohesion(word) {
    if (/^[A-Za-z][A-Za-z0-9+\-]*$/.test(word)) {
      return Math.log((this.ngramFreq.get(word) || 1)) + 1;
    }
    const arr = Array.from(word);
    if (arr.length < 2) return 0;
    const pWord = this._prob(word);
    if (pWord <= 0) return 0;
    let minPmi = Infinity;
    for (let i = 1; i < arr.length; i++) {
      const left = arr.slice(0, i).join("");
      const right = arr.slice(i).join("");
      const pl = this._prob(left);
      const pr = this._prob(right);
      if (pl <= 0 || pr <= 0) return 0;
      const pmi = Math.log(pWord / (pl * pr));
      if (pmi < minPmi) minPmi = pmi;
    }
    return minPmi === Infinity ? 0 : minPmi;
  }
  discover(opts) {
    opts = opts || {};
    const topK = opts.topK != null ? opts.topK : 80;
    const results = [];
    for (const [word, freq] of this.ngramFreq) {
      if (freq < this.minFreq) continue;
      const isAscii = /^[A-Za-z][A-Za-z0-9+\-]*$/.test(word);
      if (!isAscii) {
        const arr = Array.from(word);
        if (arr.length < this.minLen || arr.length > this.maxLen) continue;
      } else if (word.length < this.minAsciiLen) continue;
      const coh = this.cohesion(word);
      if (coh < this.minPmi) continue;
      const leftEnt = entropyOfMap(this.leftNeighbors.get(word) || new Map());
      const rightEnt = entropyOfMap(this.rightNeighbors.get(word) || new Map());
      if (leftEnt < this.minEntropy || rightEnt < this.minEntropy) continue;
      const score = freq * coh * Math.min(leftEnt, rightEnt);
      results.push({ word, freq, cohesion: coh, leftEntropy: leftEnt, rightEntropy: rightEnt, score });
    }
    results.sort((a, b) => b.score - a.score);
    const kept = [];
    for (const r of results) {
      let suppress = false;
      for (let k = 0; k < kept.length; k++) {
        const o = kept[k];
        if (o.word === r.word) continue;
        if (o.word.includes(r.word) && o.freq >= r.freq * 0.6) { suppress = true; break; }
        if (r.word.includes(o.word) && r.freq >= o.freq * 0.6 && r.word.length > o.word.length) {
          kept.splice(k, 1); k--;
        }
      }
      if (!suppress) kept.push(r);
      if (kept.length >= topK) break;
    }
    return kept;
  }
  keywordsForBlock(blockText, candidates, topN) {
    topN = topN || 5;
    const cleaned = KeywordExtractor.cleanText(blockText);
    const hits = [];
    for (const c of candidates) {
      let cnt = 0;
      let idx = 0;
      while ((idx = cleaned.indexOf(c.word, idx)) !== -1) { cnt++; idx += c.word.length; }
      if (cnt > 0) hits.push({ word: c.word, occurrences: cnt, score: c.score * Math.log(cnt + 1) });
    }
    hits.sort((a, b) => b.score - a.score);
    const out = [];
    for (const h of hits) {
      let skip = false;
      for (const o of out) {
        if (o.word.includes(h.word) || h.word.includes(o.word)) { skip = true; break; }
      }
      if (!skip) out.push(h);
      if (out.length >= topN) break;
    }
    return out.map(h => h.word);
  }
}

function detectStructuralTags(bodyText) {
  const tags = [];
  const mermaidRe = /^[ \t]*```[ \t]*mermaid\b[ \t]*\r?\n([\s\S]*?)^[ \t]*```/gm;
  let mm;
  while ((mm = mermaidRe.exec(bodyText)) !== null) {
    if (!tags.includes("mermaid")) tags.push("mermaid");
    for (const rawLine of mm[1].split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line) continue;
      if (line.startsWith("%%") || line.startsWith("---")) continue;
      const idM = line.match(/^([A-Za-z][A-Za-z0-9-]*)/);
      if (idM) {
        const dt = idM[1];
        if (dt !== "title" && !tags.includes(dt)) tags.push(dt);
      }
      break;
    }
  }
  if (/^[ \t]*```[ \t]*svg\b/m.test(bodyText) && !tags.includes("svg")) tags.push("svg");
  return tags;
}

function renderMermaidToggle(codeText) {
  const codeHtml = `<pre class="mdp-code"><button class="mdp-copy" type="button" aria-label="Copy">Copy</button><code class="language-mermaid">${esc(codeText)}</code></pre>`;
  const imgHtml = `<pre class="mermaid">${esc(codeText)}</pre>`;
  return `<div class="mdp-diagram-toggle" data-diagram="mermaid">`
    + `<div class="mdp-diagram-toolbar">`
    + `<span class="mdp-diagram-kind">mermaid</span>`
    + `<button type="button" class="mdp-diagram-btn mdp-diagram-btn-active" data-view="image">graph</button>`
    + `<button type="button" class="mdp-diagram-btn" data-view="code">code</button>`
    + `</div>`
    + `<div class="mdp-diagram-views">`
    + `<div class="mdp-diagram-view mdp-diagram-view-image mdp-diagram-view-active" data-view="image">${imgHtml}</div>`
    + `<div class="mdp-diagram-view mdp-diagram-view-code" data-view="code">${codeHtml}</div>`
    + `</div></div>`;
}

function renderSvgToggle(codeText) {
  const byteLen = (typeof TextEncoder !== "undefined") ? new TextEncoder().encode(codeText).length : codeText.length;
  const kb = (byteLen / 1024).toFixed(1);
  const codeHtml = `<pre class="mdp-code"><button class="mdp-copy" type="button" aria-label="Copy">Copy</button><code class="language-svg">${esc(codeText)}</code></pre>`;
  if (byteLen > SVG_INLINE_LIMIT_BYTES) {
    return `<div class="mdp-diagram-toggle mdp-diagram-toolarge" data-diagram="svg">`
      + `<div class="mdp-diagram-toolbar"><span class="mdp-diagram-kind">svg · ${kb} KB · too large</span></div>`
      + `<div class="mdp-diagram-views">`
      + `<aside class="mdp-callout mdp-callout-warning"><div class="mdp-callout-label">SVG 過大</div><div class="mdp-callout-body">SVG 內容 ${kb} KB,超過 16 KB 內聯閾值。建議拆成外部 <code>.svg</code> 檔,改用 <code>![alt](./diagram.svg)</code> 引用。</div></aside>`
      + codeHtml
      + `</div></div>`;
  }
  let safeSvg = codeText
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son[a-z]+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son[a-z]+\s*=\s*'[^']*'/gi, "");
  if (!/<svg[\s>]/i.test(safeSvg)) {
    safeSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><text x="10" y="38" font-size="14" fill="#94a3b8">無效的 SVG 內容</text></svg>`;
  }
  return `<div class="mdp-diagram-toggle" data-diagram="svg">`
    + `<div class="mdp-diagram-toolbar">`
    + `<span class="mdp-diagram-kind">svg · ${kb} KB</span>`
    + `<button type="button" class="mdp-diagram-btn mdp-diagram-btn-active" data-view="image">graph</button>`
    + `<button type="button" class="mdp-diagram-btn" data-view="code">code</button>`
    + `</div>`
    + `<div class="mdp-diagram-views">`
    + `<div class="mdp-diagram-view mdp-diagram-view-image mdp-diagram-view-active" data-view="image"><div class="mdp-svg-host">${safeSvg}</div></div>`
    + `<div class="mdp-diagram-view mdp-diagram-view-code" data-view="code">${codeHtml}</div>`
    + `</div></div>`;
}

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
      const langLower = lang.toLowerCase();
      if (langLower === "mermaid") {
        inner = renderMermaidToggle(codeText);
      } else if (langLower === "svg") {
        inner = renderSvgToggle(codeText);
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

function parseListMeta(s) {
  if (!s) return [];
  return s.replace(/^\[|\]$/g, "").split(",").map(x => x.trim()).filter(Boolean);
}

function renderBlockHeader(b, depth) {
  const title = b.metadata.title || b.id.replaceAll("-", " ");
  const status = b.metadata.status || "";
  const pill = status ? ` <span class="mdp-pill mdp-pill-status-${status}">${esc(status)}</span>` : "";
  const upd = b.metadata.updated ? ` <time class="mdp-updated">${esc(b.metadata.updated)}</time>` : "";
  const level = Math.min(2 + depth, 6);

  const userKws = parseListMeta(b.metadata.keywords);
  const autoKws = b._autoKeywords || [];
  const showKws = userKws.length ? userKws : autoKws;
  const kwSource = userKws.length ? "user" : "auto";
  const kwRow = showKws.length
    ? `<div class="mdp-keywords-row" data-source="${kwSource}">`
      + `<span class="mdp-keywords-label">${kwSource === "auto" ? "auto keywords" : "keywords"}</span>`
      + showKws.map(k => `<span class="mdp-keyword-chip" data-source="${kwSource}">${esc(k)}</span>`).join("")
      + `</div>`
    : "";

  return `<header class="mdp-block-header"><h${level} class="mdp-block-title">`
    + `<a class="mdp-anchor" href="#${esc(b.id)}">#</a>${esc(title)}${pill}${upd}`
    + `<span class="mdp-type-badge">${esc(b.type)}</span></h${level}>${kwRow}</header>`;
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

  // Dictionary-free auto-keyword enrichment. Skips blocks that already declare `keywords:`.
  if (opts.autoKeywords !== false && blocks.length > 0) {
    try {
      const extractor = new KeywordExtractor({
        minLen: 2, maxLen: 8, minFreq: 2, minPmi: 1.0, minEntropy: 0.4,
      });
      extractor.fit(text);
      const candidates = extractor.discover({ topK: 80 });
      const perBlock = opts.keywordsPerBlock || 5;
      for (const b of blocks) {
        if (b.metadata.keywords) continue;
        const bodyText = b.bodyLines.join("\n");
        const structural = detectStructuralTags(bodyText);
        const kws = extractor.keywordsForBlock(bodyText, candidates, perBlock);
        const merged = [...structural, ...kws.filter(k => !structural.includes(k))];
        if (merged.length) b._autoKeywords = merged;
      }
    } catch (e) { /* swallow — extraction is best-effort */ }
  }
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
  // Sidebar TOC lists only top-level blocks. Nested children remain as inline
  // `mdp-toc-inline` navs emitted by renderBlock when a parent has ≥3 non-variant
  // children — that's "其餘層級則維持導航列".
  const tocSeen = new Set();
  const tocItems = top.flatMap(b => {
    const vg = b.metadata["variant-group"];
    if (vg) { if (tocSeen.has(vg)) return []; tocSeen.add(vg); }
    const title = b.metadata.title || b.id.replaceAll("-", " ");
    const typeBadge = b.type ? ` <span class="mdp-toc-type">${esc(b.type)}</span>` : "";
    return `<li><a href="#${esc(b.id)}" data-toc-target="${esc(b.id)}" title="${esc(b.id)}">${esc(title)}${typeBadge}</a></li>`;
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
