// Markdown+ Validator — ESM module, runs in browser and Node.
// Mirrors markdown_plus_validator.py rule set.

export const VALID_TYPES = new Set([
  "document","state","history","decision","record","issue","note",
  "spec","task","reference","figure","table","chart","kpi","card",
  "gauge","targets","dashboard","dialogue","turn","step","diagram",
]);
export const VALID_STATUS = new Set([
  "draft","active","proposed","accepted","rejected","superseded",
  "deprecated","archive","healthy","degraded","down",
  "on-track","behind","exceeded","done","blocked","open","closed",
]);
export const VALID_VISIBILITY = new Set(["collapsed","hidden"]);
export const VALID_PRIORITY = new Set(["critical","high","normal","low"]);
export const PROSE_REQUIRED_TYPES = new Set(["figure","table","chart","kpi","gauge","video","audio"]);
const FORBIDDEN_RAW_TAGS = new Set([
  "div","span","section","article","aside","nav","header","footer",
  "script","style","svg","video","audio","img","table","tr","td","th",
  "ul","ol","li","p","h1","h2","h3","h4","h5","h6","details","summary","figure","figcaption",
]);

const BLOCK_HEADER_RE =
  /^(?<indent>\s*)- \*\*#(?<id>[a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])\*\*(?<meta>(?:\s+`[^`]+`)*)\s*$/;
const META_PAIR_RE = /`([a-z][a-z0-9-]*):([^`]+)`/g;
const ID_KEBAB_RE = /^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$/;
const NUMBERED_CAPTION_RE = /^\s*\*([A-Z][a-zA-Z]+)\s+\d+:/;

export function parseMetadata(s) {
  const out = {};
  for (const m of s.matchAll(META_PAIR_RE)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

export function parseBlocks(text) {
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let current = null;
  let inFence = false;
  let fenceMarker = "";
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const stripped = raw.replace(/^\s+/, "");
    if (stripped.startsWith("```") || stripped.startsWith("~~~")) {
      const marker = stripped.slice(0, 3);
      if (!inFence) { inFence = true; fenceMarker = marker; }
      else if (stripped.startsWith(fenceMarker)) { inFence = false; fenceMarker = ""; }
      if (current) current.bodyLines.push(raw);
      continue;
    }
    if (inFence) { if (current) current.bodyLines.push(raw); continue; }
    const m = BLOCK_HEADER_RE.exec(raw);
    if (m) {
      const indent = m.groups.indent.length;
      const id = m.groups.id;
      const meta = parseMetadata(m.groups.meta || "");
      current = {
        id, type: meta.type || "", metadata: meta,
        indent, line: i + 1, bodyLines: [],
        parent: null, children: [],
      };
      blocks.push(current);
    } else if (current) {
      current.bodyLines.push(raw);
    }
  }
  const stack = [];
  for (const b of blocks) {
    while (stack.length && stack[stack.length - 1].indent >= b.indent) stack.pop();
    if (stack.length) {
      b.parent = stack[stack.length - 1].id;
      stack[stack.length - 1].children.push(b.id);
    }
    stack.push(b);
  }
  return blocks;
}

function blockHasProse(b) {
  let inFenceLocal = false;
  for (const line of b.bodyLines) {
    const s = line.trim();
    if (!s) continue;
    if (s.startsWith("```") || s.startsWith("~~~")) { inFenceLocal = !inFenceLocal; continue; }
    if (inFenceLocal) continue;
    if (/^\s*\*[A-Z][a-zA-Z]+:/.test(line)) continue;
    if (s.startsWith("|") || s.startsWith("![")) continue;
    if (/[A-Za-z一-鿿]/.test(s)) return true;
  }
  return false;
}

export function validate(text) {
  const blocks = parseBlocks(text);
  const issues = [];
  const ids = new Set();

  for (const b of blocks) {
    if (!ID_KEBAB_RE.test(b.id))
      issues.push({severity:"error",line:b.line,code:"ID-001",blockId:b.id,message:`block id '${b.id}' is not valid kebab-case`});
    if (ids.has(b.id))
      issues.push({severity:"error",line:b.line,code:"ID-002",blockId:b.id,message:`duplicate block id '${b.id}'`});
    ids.add(b.id);

    if (!b.type)
      issues.push({severity:"error",line:b.line,code:"TYPE-001",blockId:b.id,message:`block '${b.id}' missing type metadata`});
    else if (!VALID_TYPES.has(b.type) && !b.type.startsWith("x-"))
      issues.push({severity:"error",line:b.line,code:"TYPE-002",blockId:b.id,message:`unknown type '${b.type}'`});

    const status = b.metadata.status;
    if (status && !VALID_STATUS.has(status))
      issues.push({severity:"warning",line:b.line,code:"STATUS-001",blockId:b.id,message:`unknown status '${status}'`});

    const vis = b.metadata.visibility;
    if (vis && !VALID_VISIBILITY.has(vis))
      issues.push({severity:"warning",line:b.line,code:"VIS-001",blockId:b.id,message:`unknown visibility '${vis}'`});

    const upd = b.metadata.updated;
    // Accept ISO 8601: date or date+time (with optional T separator, seconds, fraction, zone).
    if (upd && upd !== "unknown" && !/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$/.test(upd))
      issues.push({severity:"warning",line:b.line,code:"UPD-001",blockId:b.id,message:`updated '${upd}' not ISO 8601`});

    if ((status === "deprecated" || status === "superseded") && !b.metadata["superseded-by"])
      issues.push({severity:"error",line:b.line,code:"DEP-001",blockId:b.id,message:`status:${status} requires superseded-by`});

    if (b.type === "history" && b.metadata.visibility !== "collapsed")
      issues.push({severity:"warning",line:b.line,code:"HIST-001",blockId:b.id,message:`type:history should have visibility:collapsed`});

    if (b.type === "kpi" && !b.metadata.value)
      issues.push({severity:"error",line:b.line,code:"KPI-001",blockId:b.id,message:`type:kpi missing value`});

    if (b.type === "gauge") {
      for (const req of ["value","min","max","target","zones"]) {
        if (!b.metadata[req])
          issues.push({severity:"error",line:b.line,code:"GAUGE-001",blockId:b.id,message:`type:gauge missing ${req}`});
      }
    }

    if (PROSE_REQUIRED_TYPES.has(b.type) && !blockHasProse(b))
      issues.push({severity:"error",line:b.line,code:"PROSE-001",blockId:b.id,message:`type:${b.type} missing prose companion`});
  }

  // Global checks
  for (const b of blocks) {
    const sb = b.metadata["superseded-by"];
    if (sb && !blocks.some(x => x.id === sb))
      issues.push({severity:"error",line:b.line,code:"XREF-001",blockId:b.id,message:`superseded-by:${sb} not found`});
  }

  const lines = text.split(/\r?\n/);
  let inFence = false, fenceMarker = "";
  let tableStart = null, tableRows = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const stripped = line.replace(/^\s+/, "");
    if (stripped.startsWith("```") || stripped.startsWith("~~~")) {
      const m = stripped.slice(0,3);
      if (!inFence) { inFence = true; fenceMarker = m; }
      else if (stripped.startsWith(fenceMarker)) { inFence = false; fenceMarker = ""; }
      continue;
    }
    if (inFence) continue;

    if (/^\s*:::/.test(line))
      issues.push({severity:"error",line:i+1,code:"FENCE-001",message:`':::' directive not allowed`});

    if (/data:[a-z]+\/[a-z+.-]+;base64,/i.test(line))
      issues.push({severity:"error",line:i+1,code:"BASE64-001",message:`inline base64 not allowed`});

    // Strip inline-code spans before scanning so prose can legitimately reference
    // `<script>` / `<svg>` etc. inside backticks without tripping the rule.
    const lineForHtmlScan = line.replace(/`[^`]*`/g, " ");

    if (/<\s*svg\b/i.test(lineForHtmlScan))
      issues.push({severity:"error",line:i+1,code:"SVG-001",message:`inline <svg> not allowed (wrap in \`\`\`svg fence or use ![alt](./file.svg))`});

    // raw HTML
    const tagMatches = lineForHtmlScan.matchAll(/<\s*\/?\s*([a-zA-Z][a-zA-Z0-9]*)\b/g);
    for (const tm of tagMatches) {
      const tag = tm[1].toLowerCase();
      if (FORBIDDEN_RAW_TAGS.has(tag))
        issues.push({severity:"error",line:i+1,code:"HTML-001",message:`raw HTML tag <${tag}> not allowed`});
    }

    if (NUMBERED_CAPTION_RE.test(line))
      issues.push({severity:"warning",line:i+1,code:"CAP-NUM-001",message:`caption has hardcoded number`});

    if (/^\s*\|.*\|\s*$/.test(line)) {
      if (tableStart === null) tableStart = i + 1;
      tableRows++;
    } else {
      if (tableStart !== null && tableRows > 30)
        issues.push({severity:"warning",line:tableStart,code:"TBL-SIZE-001",message:`table ${tableRows} rows; use data-source`});
      tableStart = null; tableRows = 0;
    }
  }

  // variant-group checks
  const byGroup = new Map();
  for (const b of blocks) {
    const vg = b.metadata["variant-group"];
    if (vg) {
      const key = `${b.parent || "_root_"}|${vg}`;
      if (!byGroup.has(key)) byGroup.set(key, []);
      byGroup.get(key).push(b);
    }
  }
  for (const [key, siblings] of byGroup) {
    const variants = siblings.map(s => s.metadata.variant);
    if (variants.some(v => !v))
      issues.push({severity:"error",line:siblings[0].line,code:"VARIANT-001",message:`variant-group sibling missing variant`});
    if (new Set(variants).size !== variants.length)
      issues.push({severity:"error",line:siblings[0].line,code:"VARIANT-002",message:`variant-group has duplicate variants`});
  }

  issues.sort((a,b) => a.line - b.line || a.code.localeCompare(b.code));
  return { blocks, issues, pass: issues.every(x => x.severity !== "error") };
}
