"""
mdp — Markdown+ block query CLI.

Lets a human or a script do progressive disclosure on a Markdown+ document
without reading the whole file. Same logic the /api/mdp/* HTTP endpoints use.

Usage — read (query API, Layer 2):
    python mdp.py list   <doc.mdp.md> [--depth N] [--type T] [--status S] [--where k=v ...] [--json]
    python mdp.py tree   <doc.mdp.md> [--json]
    python mdp.py get    <doc.mdp.md> <block-id> [--json]
    python mdp.py children <doc.mdp.md> <block-id> [--json]
    python mdp.py read   <doc.mdp.md> <block-id> [--children] [--max-lines N]
    python mdp.py search <doc.mdp.md> <query> [--limit N] [--json]
    python mdp.py xref   <doc.mdp.md> <block-id> [--json]

Usage — write (edit API, Layer 4):
    python mdp.py set-body <doc.mdp.md> <block-id> <new-body | ->     (- reads stdin)
    python mdp.py set-meta <doc.mdp.md> <block-id> key=val [key=val ...]   (key=- removes a key)
    python mdp.py add      <doc.mdp.md> --id <id> --type <type> [--parent <id> | --after <id>] [--meta k=v ...] [--body <text | ->]
    python mdp.py archive  <doc.mdp.md> <block-id> --superseded-by <id>

Exit code 0 = ok, 1 = error (e.g. block id not found), 2 = bad usage.
"""
from __future__ import annotations

import json
import sys

import edit as ed
import query as q

USAGE = __doc__


def _split_args(argv: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Separate positional args from --flags. Repeatable flags accumulate."""
    positional: list[str] = []
    flags: dict[str, list[str]] = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            # boolean flags vs value flags
            if key in ("json", "children"):
                flags.setdefault(key, []).append("true")
            else:
                i += 1
                if i >= len(argv):
                    raise SystemExit(f"flag --{key} needs a value")
                flags.setdefault(key, []).append(argv[i])
        else:
            positional.append(a)
        i += 1
    return positional, flags


def _build_where(flags: dict[str, list[str]]) -> dict[str, str]:
    where: dict[str, str] = {}
    if "type" in flags:
        where["type"] = flags["type"][-1]
    if "status" in flags:
        where["status"] = flags["status"][-1]
    if "parent" in flags:
        where["parent"] = flags["parent"][-1]
    for pair in flags.get("where", []):
        if "=" not in pair:
            raise SystemExit(f"--where expects k=v, got {pair!r}")
        k, v = pair.split("=", 1)
        where[k] = v
    return where


def _emit(obj, as_json: bool, human) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        human(obj)


def _print_manifest(rows: list[dict]) -> None:
    if not rows:
        print("(no blocks)")
        return
    for r in rows:
        status = r.get("status") or "-"
        print(f"  L{r.get('line', 0):>4}  #{r.get('id', ''):<28} "
              f"{r.get('type', ''):<12} {status:<12} {r.get('title', '')}")
    print(f"  ({len(rows)} blocks)")


def _print_tree(nodes: list[dict], indent: int = 0) -> None:
    for n in nodes:
        status = f" [{n['status']}]" if n.get("status") else ""
        print(f"{'  ' * indent}- #{n['id']} ({n['type']}){status}  {n['title']}")
        _print_tree(n.get("children", []), indent + 1)


def _print_meta(m: dict) -> None:
    print(f"#{m['id']}  type:{m['type']}  line:{m['line']}  depth:{m['depth']}")
    print(f"  title:    {m['title']}")
    if m.get("summary"):
        print(f"  summary:  {m['summary']}")
    print(f"  parent:   {m['parent'] or '-'}")
    print(f"  children: {', '.join(m['children']) or '-'}")
    print(f"  body:     {m['body_line_count']} lines")
    if m["metadata"]:
        print("  metadata:")
        for k, v in m["metadata"].items():
            print(f"    {k}: {v}")


def _print_xref(x: dict) -> None:
    def fmt(ref):
        if ref is None:
            return "-"
        if not ref.get("found", True):
            return f"#{ref['id']} (NOT FOUND)"
        return f"#{ref['id']} ({ref['type']})"

    print(f"#{x['id']}")
    print(f"  parent:        {fmt(x['parent'])}")
    print(f"  children:      {', '.join(fmt(c) for c in x['children']) or '-'}")
    print(f"  superseded-by: {fmt(x['superseded_by'])}")
    print(f"  supersedes:    {', '.join(fmt(s) for s in x['supersedes']) or '-'}")
    print(f"  related:       {', '.join(fmt(r) for r in x['related']) or '-'}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE)
        return 2
    cmd = argv[1]
    try:
        positional, flags = _split_args(argv[2:])
    except SystemExit as e:
        print(e)
        return 2

    as_json = "json" in flags

    try:
        if cmd == "list":
            if len(positional) < 1:
                print("usage: mdp.py list <doc> [--depth N] [--type T] [--status S]")
                return 2
            depth = int(flags["depth"][-1]) if "depth" in flags else None
            where = _build_where(flags)
            rows = q.list_blocks(positional[0], depth=depth, where=where or None)
            _emit(rows, as_json, _print_manifest)

        elif cmd == "tree":
            if len(positional) < 1:
                print("usage: mdp.py tree <doc>")
                return 2
            nodes = q.tree(positional[0])
            _emit(nodes, as_json, _print_tree)

        elif cmd == "get":
            if len(positional) < 2:
                print("usage: mdp.py get <doc> <block-id>")
                return 2
            meta = q.get_block_meta(positional[0], positional[1])
            _emit(meta, as_json, _print_meta)

        elif cmd == "children":
            if len(positional) < 2:
                print("usage: mdp.py children <doc> <block-id>")
                return 2
            ids = q.list_children(positional[0], positional[1])
            _emit(ids, as_json, lambda xs: print("\n".join(f"  #{i}" for i in xs) or "(none)"))

        elif cmd == "read":
            if len(positional) < 2:
                print("usage: mdp.py read <doc> <block-id> [--children] [--max-lines N]")
                return 2
            max_lines = int(flags["max-lines"][-1]) if "max-lines" in flags else None
            res = q.read_block(
                positional[0], positional[1],
                include_children="children" in flags,
                max_lines=max_lines,
            )
            if as_json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(res["body"])
                if res["truncated"]:
                    print(f"\n... [truncated at {max_lines} lines]", file=sys.stderr)

        elif cmd == "search":
            if len(positional) < 2:
                print("usage: mdp.py search <doc> <query> [--limit N]")
                return 2
            limit = int(flags["limit"][-1]) if "limit" in flags else 20
            rows = q.search_blocks(positional[0], positional[1], limit=limit)
            _emit(rows, as_json, _print_manifest)

        elif cmd == "xref":
            if len(positional) < 2:
                print("usage: mdp.py xref <doc> <block-id>")
                return 2
            x = q.resolve_xref(positional[0], positional[1])
            _emit(x, as_json, _print_xref)

        # --- write commands (edit API, Layer 4) ---

        elif cmd == "set-body":
            if len(positional) < 3:
                print("usage: mdp.py set-body <doc> <block-id> <new-body | ->")
                return 2
            body = sys.stdin.read() if positional[2] == "-" else positional[2]
            res = ed.update_block_body(positional[0], positional[1], body)
            _emit(res, as_json, lambda r: print(
                f"updated #{r['id']} body: {r['old_body_lines']} → {r['new_body_lines']} lines"))

        elif cmd == "set-meta":
            if len(positional) < 3:
                print("usage: mdp.py set-meta <doc> <block-id> key=val [key=val ...]  (key=- removes)")
                return 2
            patch: dict[str, str | None] = {}
            for pair in positional[2:]:
                if "=" not in pair:
                    print(f"set-meta expects key=val, got {pair!r}", file=sys.stderr)
                    return 2
                k, v = pair.split("=", 1)
                patch[k] = None if v == "-" else v
            res = ed.update_block_metadata(positional[0], positional[1], patch)
            _emit(res, as_json, lambda r: print(
                f"updated #{r['id']} metadata: " + " ".join(f"{k}:{v}" for k, v in r["metadata"].items())))

        elif cmd == "add":
            if len(positional) < 1 or "id" not in flags or "type" not in flags:
                print("usage: mdp.py add <doc> --id <id> --type <type> "
                      "[--parent <id> | --after <id>] [--meta k=v ...] [--body <text | ->]")
                return 2
            meta: dict[str, str] = {}
            for pair in flags.get("meta", []):
                if "=" not in pair:
                    print(f"--meta expects k=v, got {pair!r}", file=sys.stderr)
                    return 2
                k, v = pair.split("=", 1)
                meta[k] = v
            body_arg = flags["body"][-1] if "body" in flags else ""
            body = sys.stdin.read() if body_arg == "-" else body_arg
            block = {"id": flags["id"][-1], "type": flags["type"][-1],
                     "metadata": meta, "body": body}
            res = ed.add_block(
                positional[0], block,
                parent_id=flags["parent"][-1] if "parent" in flags else None,
                after_id=flags["after"][-1] if "after" in flags else None,
            )
            _emit(res, as_json, lambda r: print(
                f"added #{r['id']} (indent {r['indent']}, {r['placement']}) after line {r['after_line']}"))

        elif cmd == "archive":
            if len(positional) < 2 or "superseded-by" not in flags:
                print("usage: mdp.py archive <doc> <block-id> --superseded-by <id>")
                return 2
            res = ed.archive_block(positional[0], positional[1],
                                   superseded_by=flags["superseded-by"][-1])
            _emit(res, as_json, lambda r: print(
                f"archived #{r['id']} → status:deprecated superseded-by:{r['metadata'].get('superseded-by')}"))

        else:
            print(f"unknown command {cmd!r}\n")
            print(USAGE)
            return 2

    except FileNotFoundError as e:
        print(f"file not found: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
