// Markdown+ rewriter — Node.js wrapper around OpenAI Responses API.
// Usage:
//   OPENAI_API_KEY=sk-... node rewriter.mjs --from markdown input.md > output.mdp.md
//   OPENAI_API_KEY=sk-... node rewriter.mjs --from html     input.html > output.mdp.md
//   cat input.md | OPENAI_API_KEY=sk-... node rewriter.mjs --from markdown - > output.mdp.md
//
// Requires:  npm install openai

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import OpenAI from "openai";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const args = { input: null, from: null, model: process.env.REWRITER_MODEL || "gpt-5.5", effort: process.env.REWRITER_EFFORT || "none" };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--from") args.from = argv[++i];
    else if (a === "--model") args.model = argv[++i];
    else if (a === "--effort") args.effort = argv[++i];
    else if (a.startsWith("--")) throw new Error(`Unknown flag ${a}`);
    else args.input = a;
  }
  if (!args.from || !args.input) {
    console.error("usage: node rewriter.mjs --from markdown|html <input|->");
    process.exit(2);
  }
  return args;
}

function readInput(p) {
  if (p === "-") {
    return fs.readFileSync(0, "utf-8");
  }
  return fs.readFileSync(p, "utf-8");
}

function buildPrompt(kind, content) {
  const tmplPath = path.join(__dirname, "prompts", kind === "markdown" ? "from_markdown.txt" : "from_html.txt");
  const tmpl = fs.readFileSync(tmplPath, "utf-8");
  const placeholder = kind === "markdown" ? "{{markdown_doc}}" : "{{html_doc}}";
  return tmpl.split(placeholder).join(content);
}

async function main() {
  if (!process.env.OPENAI_API_KEY) {
    console.error("ERROR: OPENAI_API_KEY not set");
    process.exit(1);
  }
  const args = parseArgs(process.argv);
  const content = readInput(args.input);
  const prompt = buildPrompt(args.from, content);

  const client = new OpenAI();
  const response = await client.responses.create({
    model: args.model,
    input: prompt,
    reasoning: { effort: args.effort },
  });
  process.stdout.write(response.output_text || "");
}

main().catch(e => { console.error(e); process.exit(1); });
