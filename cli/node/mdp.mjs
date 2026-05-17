// mdp — Markdown+ block query CLI (Node ESM).
//
// Lets a human or a script do progressive disclosure on a Markdown+ document
// without reading the whole file. Mirrors cli/python/mdp.py.
//
// Usage:
//   node mdp.mjs list   <doc.mdp.md> [--depth N] [--type T] [--status S] [--where k=v ...] [--json]
//   node mdp.mjs tree   <doc.mdp.md> [--json]
//   node mdp.mjs get    <doc.mdp.md> <block-id> [--json]
//   node mdp.mjs children <doc.mdp.md> <block-id> [--json]
//   node mdp.mjs read   <doc.mdp.md> <block-id> [--children] [--max-lines N]
//   node mdp.mjs search <doc.mdp.md> <query> [--limit N] [--json]
//   node mdp.mjs xref   <doc.mdp.md> <block-id> [--json]
//
// Exit code 0 = ok, 1 = error (e.g. block id not found), 2 = bad usage.

import * as q from "./query.mjs";

const USAGE = `mdp — Markdown+ block query CLI

  node mdp.mjs list   <doc> [--depth N] [--type T] [--status S] [--where k=v ...] [--json]
  node mdp.mjs tree   <doc> [--json]
  node mdp.mjs get    <doc> <block-id> [--json]
  node mdp.mjs children <doc> <block-id> [--json]
  node mdp.mjs read   <doc> <block-id> [--children] [--max-lines N]
  node mdp.mjs search <doc> <query> [--limit N] [--json]
  node mdp.mjs xref   <doc> <block-id> [--json]`;

const BOOL_FLAGS = new Set(["json", "children"]);

function splitArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      if (BOOL_FLAGS.has(key)) {
        (flags[key] ||= []).push("true");
      } else {
        i += 1;
        if (i >= argv.length) { console.error(`flag --${key} needs a value`); process.exit(2); }
        (flags[key] ||= []).push(argv[i]);
      }
    } else {
      positional.push(a);
    }
  }
  return { positional, flags };
}

function buildWhere(flags) {
  const where = {};
  if (flags.type) where.type = flags.type.at(-1);
  if (flags.status) where.status = flags.status.at(-1);
  if (flags.parent) where.parent = flags.parent.at(-1);
  for (const pair of flags.where || []) {
    const eq = pair.indexOf("=");
    if (eq === -1) { console.error(`--where expects k=v, got '${pair}'`); process.exit(2); }
    where[pair.slice(0, eq)] = pair.slice(eq + 1);
  }
  return where;
}

function printManifest(rows) {
  if (!rows.length) { console.log("(no blocks)"); return; }
  for (const r of rows) {
    const status = r.status || "-";
    console.log(
      `  L${String(r.line ?? 0).padStart(4)}  #${String(r.id ?? "").padEnd(28)} ` +
      `${String(r.type ?? "").padEnd(12)} ${String(status).padEnd(12)} ${r.title ?? ""}`
    );
    // `snippets` is search-only — each entry shows where the keyword actually
    // hit, with `…` marking truncation. Skipped silently for list/tree output.
    for (const snip of r.snippets || []) {
      console.log(`        ↳ [${snip.field}] ${snip.snippet}`);
    }
  }
  console.log(`  (${rows.length} blocks)`);
}

function printTree(nodes, indent = 0) {
  for (const n of nodes) {
    const status = n.status ? ` [${n.status}]` : "";
    console.log(`${"  ".repeat(indent)}- #${n.id} (${n.type})${status}  ${n.title}`);
    printTree(n.children || [], indent + 1);
  }
}

function printMeta(m) {
  console.log(`#${m.id}  type:${m.type}  line:${m.line}  depth:${m.depth}`);
  console.log(`  title:    ${m.title}`);
  if (m.summary) console.log(`  summary:  ${m.summary}`);
  console.log(`  parent:   ${m.parent || "-"}`);
  console.log(`  children: ${m.children.join(", ") || "-"}`);
  console.log(`  body:     ${m.body_line_count} lines`);
  if (Object.keys(m.metadata).length) {
    console.log("  metadata:");
    for (const [k, v] of Object.entries(m.metadata)) console.log(`    ${k}: ${v}`);
  }
}

function printXref(x) {
  const fmt = (ref) => {
    if (!ref) return "-";
    if (ref.found === false) return `#${ref.id} (NOT FOUND)`;
    return `#${ref.id} (${ref.type})`;
  };
  console.log(`#${x.id}`);
  console.log(`  parent:        ${fmt(x.parent)}`);
  console.log(`  children:      ${x.children.map(fmt).join(", ") || "-"}`);
  console.log(`  superseded-by: ${fmt(x.superseded_by)}`);
  console.log(`  supersedes:    ${x.supersedes.map(fmt).join(", ") || "-"}`);
  console.log(`  related:       ${x.related.map(fmt).join(", ") || "-"}`);
}

function emit(obj, asJson, human) {
  if (asJson) console.log(JSON.stringify(obj, null, 2));
  else human(obj);
}

function main(argv) {
  if (argv.length < 3) { console.log(USAGE); return 2; }
  const cmd = argv[2];
  const { positional, flags } = splitArgs(argv.slice(3));
  const asJson = "json" in flags;

  try {
    switch (cmd) {
      case "list": {
        if (positional.length < 1) { console.log("usage: mdp.mjs list <doc> [--depth N] [--type T] [--status S]"); return 2; }
        const depth = flags.depth ? parseInt(flags.depth.at(-1), 10) : null;
        const where = buildWhere(flags);
        const rows = q.listBlocks(positional[0], { depth, where: Object.keys(where).length ? where : null });
        emit(rows, asJson, printManifest);
        break;
      }
      case "tree": {
        if (positional.length < 1) { console.log("usage: mdp.mjs tree <doc>"); return 2; }
        emit(q.tree(positional[0]), asJson, printTree);
        break;
      }
      case "get": {
        if (positional.length < 2) { console.log("usage: mdp.mjs get <doc> <block-id>"); return 2; }
        emit(q.getBlockMeta(positional[0], positional[1]), asJson, printMeta);
        break;
      }
      case "children": {
        if (positional.length < 2) { console.log("usage: mdp.mjs children <doc> <block-id>"); return 2; }
        const ids = q.listChildren(positional[0], positional[1]);
        emit(ids, asJson, (xs) => console.log(xs.map((i) => `  #${i}`).join("\n") || "(none)"));
        break;
      }
      case "read": {
        if (positional.length < 2) { console.log("usage: mdp.mjs read <doc> <block-id> [--children] [--max-lines N]"); return 2; }
        const maxLines = flags["max-lines"] ? parseInt(flags["max-lines"].at(-1), 10) : null;
        const res = q.readBlock(positional[0], positional[1], {
          includeChildren: "children" in flags,
          maxLines,
        });
        if (asJson) {
          console.log(JSON.stringify(res, null, 2));
        } else {
          console.log(res.body);
          if (res.truncated) console.error(`\n... [truncated at ${maxLines} lines]`);
        }
        break;
      }
      case "search": {
        if (positional.length < 2) { console.log("usage: mdp.mjs search <doc> <query> [--limit N]"); return 2; }
        const limit = flags.limit ? parseInt(flags.limit.at(-1), 10) : 20;
        emit(q.searchBlocks(positional[0], positional[1], { limit }), asJson, printManifest);
        break;
      }
      case "xref": {
        if (positional.length < 2) { console.log("usage: mdp.mjs xref <doc> <block-id>"); return 2; }
        emit(q.resolveXref(positional[0], positional[1]), asJson, printXref);
        break;
      }
      default:
        console.log(`unknown command '${cmd}'\n`);
        console.log(USAGE);
        return 2;
    }
  } catch (e) {
    console.error(`error: ${e.message}`);
    return 1;
  }
  return 0;
}

process.exit(main(process.argv));
