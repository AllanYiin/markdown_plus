"""
Markdown+ rewriter — thin wrapper around OpenAI Responses API.

Usage:
    set OPENAI_API_KEY=sk-...
    python rewriter.py --from markdown input.md > output.mdp.md
    python rewriter.py --from html     input.html > output.mdp.md
    cat input.md | python rewriter.py --from markdown - > output.mdp.md

Options:
    --model         default: gpt-5.5
    --effort        reasoning.effort, default: none
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent
PROMPTS = {
    "markdown": ROOT / "prompts" / "from_markdown.txt",
    "html": ROOT / "prompts" / "from_html.txt",
}


def build_prompt(kind: str, content: str) -> str:
    tmpl = PROMPTS[kind].read_text(encoding="utf-8")
    placeholder = "{{markdown_doc}}" if kind == "markdown" else "{{html_doc}}"
    return tmpl.replace(placeholder, content)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", help="input file path or '-' for stdin")
    p.add_argument("--from", dest="kind", choices=["markdown", "html"], required=True)
    p.add_argument("--model", default=os.environ.get("REWRITER_MODEL", "gpt-5.5"))
    p.add_argument("--effort", default=os.environ.get("REWRITER_EFFORT", "none"))
    args = p.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 1

    if args.input == "-":
        content = sys.stdin.read()
    else:
        content = Path(args.input).read_text(encoding="utf-8")

    prompt = build_prompt(args.kind, content)

    client = OpenAI()
    response = client.responses.create(
        model=args.model,
        input=prompt,
        reasoning={"effort": args.effort},
    )
    sys.stdout.write(response.output_text or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
