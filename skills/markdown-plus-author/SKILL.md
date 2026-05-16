---
name: markdown-plus-author
description: Write or revise Markdown+ documents — plain Markdown that stays valid in any markdown viewer while adding bullet-list blocks with `**#id**` headers, inline-code `key:value` metadata, and viewer-side projection cues. Use when the user asks to write or rewrite a dev note, decision record, research report, tech spec, status report, executive brief, runbook, ADR, status report, or any AI-readable structured document; or when the user asks to convert plain Markdown or existing HTML into Markdown+. Do not use for slide decks, email drafts, or one-off short replies. Successful output is a single CommonMark-valid Markdown file whose blocks can be queried by a parser and projected into human-friendly HTML, with no `:::` fences, no raw HTML wrappers, no base64, code fences and ASCII trees preserved verbatim, and a prose companion for every figure/table/chart.
---

# Markdown+ Author

<role>
Act as a structured-document author who treats Markdown as the AI work surface and HTML as a human projection. Produce source that is simultaneously valid plain Markdown and richly queryable by parsers.
</role>

<decision_boundary>
Use when:
- The user asks to write a dev note, decision record, research report, tech spec, status report, exec brief, runbook, or any AI-readable structured document in Markdown+.
- The user asks to rewrite plain Markdown or HTML into Markdown+.
- The user asks how Markdown+ syntax works or how to add metadata.

Do not use when:
- The user wants a presentation deck, slides, or pptx.
- The user wants a one-off short message, email body, or chat reply.
- The user explicitly requests raw HTML or another non-Markdown format as the final output.
- The user wants a paper / essay where flowing prose matters more than block-addressability.

Successful output:
- Single Markdown file.
- Every substantive section is a bullet-list block with `**#id**` header and inline-code metadata.
- Parses cleanly in standard CommonMark viewers (GitHub, Obsidian, VS Code preview) without showing unrendered directives.
- Every figure, table, chart, video, audio block has a prose companion paragraph.
- All binary media referenced by relative path, never base64.
</decision_boundary>

<spirit>
Markdown+ is not a new format. It is plain Markdown plus three habits:
1. Substantive sections are bullet-list items headed by `**#id**` with inline-code `key:value` metadata.
2. Binary media and large datasets stay external via relative paths.
3. Every figure, table, chart, KPI carries a prose companion sentence.

Three principles drive every decision:
- **Graceful degradation**: source must remain valid CommonMark. Never use `:::` fences, raw HTML wrappers, custom directives, or any syntax that renders as gibberish in a vanilla markdown viewer.
- **Source for AI, projection for humans**: source carries semantics (metadata + prose); a viewer adds visual richness (nav, pills, gauges, callouts, cards). The source itself does not encode visual styling.
- **No inline binary**: image, video, audio are always referenced by relative path. Base64 / data-URI in source is a hard lint error. SVG is a text format and is permitted inside ` ```svg ` code fences up to 16 KB; anything larger must move to an external `.svg` file.
</spirit>

<workflow>
Step 1: Detect input type.
- Input: the user's request and any provided content.
- Action: classify as `fresh_write` (no input doc), `rewrite_markdown` (plain Markdown provided), or `rewrite_html` (HTML provided).
- Output: input type label + raw content.
- Validation: if HTML, scan for `base64,` or `<script>`. If present, plan to strip script and either ask for external media path or extract media to `./media/` before proceeding.

Step 2: Plan the block manifest before writing any block body.
- Input: the raw content (or topic + scenario for fresh writes).
- Action: enumerate intended blocks as `(id, type, title)` triples in document order. Decide nesting depth from the input's section/heading structure (HTML `<section>` / Markdown `##` → top-level block; nested headings → child blocks).
- Output: block manifest.
- Validation: if the manifest contains fewer than 2 substantive blocks, ask the user whether a single prose paragraph would serve better than Markdown+.

Step 3: Assign block types from the controlled vocabulary.
- Input: the manifest from Step 2.
- Action: assign each block a `type:` from `references/metadata-vocabulary.md`. Common types: `state`, `history`, `decision`, `record`, `issue`, `note`, `spec`, `task`, `reference`, `figure`, `table`, `chart`, `kpi`, `card`, `gauge`, `targets`, `dashboard`, `dialogue`, `step`.
- Output: typed manifest.
- Validation: every block has exactly one `type:` value from the closed vocabulary (or an `x-` prefixed extension with a documented fallback projection).

Step 4: Write each block.
- Input: the typed manifest + content per block.
- Action: write each block as a bullet-list item. The first line is the block header pattern:
  ```
  - **#<kebab-case-id>** `type:<value>` `status:<value>` `updated:YYYY-MM-DD` ...
  ```
  Body content follows on the next line, indented 2 spaces. Use nested bullet lists for parent–child relationships. Use H1 only once (document title); within blocks use H3/H4 sparingly.
- Output: draft Markdown+ document.
- Validation: every block has `**#id**` + at least `type:` metadata. IDs are kebab-case, unique within the document, and stable.
- **Verbatim preservation (hard rule)**: when the source contains a fenced code block (```` ``` ````), an ASCII tree / directory structure / box-drawing art (`│ ├ └ ─`), or an aligned table, the rewrite MUST keep that content **1:1 byte-for-byte** inside a fenced code block; do not collapse multi-line trees into a single paragraph, do not "tidy" alignment, do not drop the fence. See `references/code-fence-preservation.md`.

Step 5: Add captions and prose companions.
- Input: draft from Step 4.
- Action: directly above every table, code fence, image, video, audio, chart block, add an italic caption line: `*Caption: ...*` (or `*Table: ...*`, `*Figure: ...*`, `*Listing: ...*`). Below every figure/chart/video block, add at least one prose sentence describing the visible content.
- Output: captioned draft.
- Validation: captions contain no hardcoded numbers like "Figure 1:" or "Table 3:"; the viewer auto-numbers from manifest order.

Step 6: Apply enhancement metadata where it adds value.
- Input: captioned draft.
- Action: where the document has parallel siblings (e.g. install steps for mac/linux/windows), add `variant-group:<name>` + `variant:<value>` to each. Add `sortable:true`, `searchable:true`, or `summary-row:sum` to tables that benefit. Add `value:`, `target:`, `delta:` to KPI/gauge blocks. Add `speaker:` to dialogue turns. Tables exceeding ~30 rows get `data-source:./data/<name>.csv` instead of inline data.
- Output: enhanced draft.

Step 7: Validate against output contract.
- Input: enhanced draft.
- Action: run the validation checklist in `<output_contract>` below. Every failure must be fixed before output.
- Output: final Markdown+.
</workflow>

<output_contract>
Return only the Markdown+ document. No preamble, no trailing explanation, no surrounding code fence (do not wrap the entire output in ``` ``` ```).

Document structure (exact order):
1. A single `#` H1 line containing the document title.
2. (Optional) one short plain-prose introduction paragraph.
3. One or more top-level bullet-list blocks. Each top-level block follows the block header pattern.

Block header pattern (mandatory for every substantive block):
```
- **#<kebab-case-id>** `type:<value>` [`<key>:<value>` ...]
  <body content, indented 2 spaces, any valid Markdown>

  - **#<child-id>** `type:<value>` [`<key>:<value>` ...]
    <nested body, indented 4 spaces>
```

Validation rules (all must PASS before output):
- [ ] Every block has `**#<id>**` with a kebab-case id, unique in the document.
- [ ] Every block has `type:` from the controlled vocabulary in `references/metadata-vocabulary.md`.
- [ ] No `:::` fences anywhere.
- [ ] No raw HTML tags except `<br>`, `<hr>`, `<sub>`, `<sup>` and only when the equivalent Markdown is unavailable.
- [ ] No `data:` URIs, no `base64,`, no inline binary anywhere.
- [ ] No raw `<svg>` written directly in prose or inside an HTML container. SVG belongs inside a ` ```svg ` code fence (when ≤ 16 KB) or as an external file referenced via `![alt](./diagrams/<name>.svg)` (when larger). Diagram authors are encouraged to prefer ` ```svg ` fences when the markup is hand-written and small, because the viewer renders it inline with a `graph` / `code` toggle.
- [ ] Mermaid diagrams use ` ```mermaid ` fences. The viewer renders them with the same `graph` / `code` toggle and auto-tags the block with the diagram type (`sequenceDiagram` / `flowchart` / `classDiagram` / `gantt` / `graph` / ...) extracted from the fence's first content line — authors do not need to repeat that in metadata.
- [ ] Every `type:figure`, `type:chart`, `type:table`, `type:kpi`, `type:gauge` block has a prose companion paragraph (≥1 sentence) describing or explaining the embedded content.
- [ ] Every table with more than ~30 rows uses `data-source:./data/<name>.csv` instead of inline rows.
- [ ] Captions contain no hardcoded numbers; format is `*<Kind>: <description>*` (e.g. `*Table: Q1 月度營收*`).
- [ ] `status:deprecated` blocks have `superseded-by:<id>` pointing to a valid id in the same document.
- [ ] `type:history` and archive blocks have `visibility:collapsed`.
- [ ] Sibling blocks sharing `variant-group:` each have a distinct `variant:` value.
- [ ] `type:kpi` blocks have both `value:` in metadata and the same number stated in the prose paragraph.
- [ ] **Code fences and ASCII trees in the source are preserved verbatim**: no flattening multi-line tree art into prose, no dropping fence markers, no "tidying" alignment. Multi-line content with box-drawing characters (`│ ├ └ ─`) lives inside a fenced code block.
- [ ] The document is valid CommonMark: opening it in a vanilla markdown viewer shows nested bullet lists, inline code, italic captions, and standard tables — never unrendered directives.
</output_contract>

<default_follow_through_policy>
Direct action (no ask needed):
- Choose block ids, types, and metadata when the input is unambiguous.
- Reformat plain Markdown headings into bullet-list blocks.
- Move binary media references to relative paths when the input pointed to local absolute paths.
- Strip inline HTML wrappers from input HTML when their content has a clean Markdown equivalent.
- Strip `<script>`, `<style>`, and CSS class attributes from input HTML (they belong in the viewer, not the source).

Ask first:
- The input HTML contains `data:image/...;base64,...`. Stop and ask the user to provide an external file path or extract+save the binary.
- The input contains charts as inline JS configurations (Highcharts, Chart.js, plotly) exceeding ~80 lines. Ask whether to extract to `./charts/<name>.json` or keep inline as a `chart-type:` fence.
- A document level has >50 sibling blocks. Ask whether to reorganize into a deeper hierarchy.
- The input is genuinely ambiguous about which sections are substantive vs incidental. Ask for guidance rather than guessing.

Stop and report:
- The input contains apparent secret strings (API keys, tokens). Do not echo them back; report and ask for sanitized input.
- The input is not Markdown or HTML (binary file, image, audio attached). Report and ask for textual input.
- The input mixes Markdown+ and `:::block` syntax. Report the inconsistency and ask which canonical form to use.
- The input contains an ASCII tree / table / box-drawing art that is **not** already wrapped in a code fence. Do not silently wrap it during rewrite; ask the user whether the alignment is meaningful (if yes, wrap in ``` fence; if no, ask whether to remove). Never flatten multi-line aligned art into prose.
</default_follow_through_policy>

<viewer_features>
The Markdown+ reference viewer (browser + lib/mdp-viewer.mjs) layers several
projections on top of plain source. None of these require any author action
beyond writing valid Markdown+ — they are derived automatically from source so
the AI surface stays clean. Authors should know they exist so they don't
re-encode the same information manually.

- **SVG fence inline rendering**: a ` ```svg ` code fence ≤ 16 KB is rendered
  with a `graph` / `code` toggle (toolbar shows the byte size). The viewer
  sanitizes `<script>` and `on*=` event handlers before injection; structural
  markers (`<defs>`, `<style>`, `<marker>`, `<filter>`) are preserved. Over
  16 KB the viewer refuses to inline and shows a warning callout asking the
  author to externalize. The 16 KB threshold balances "icons and simple
  diagrams stay readable in source" against "complex charts pollute the file".

- **Mermaid fence inline rendering**: a ` ```mermaid ` fence shares the same
  `graph` / `code` toggle. The viewer dynamically imports Mermaid 10 from CDN
  and renders to SVG in the `graph` view; the `code` view shows raw mermaid
  source. The viewer extracts the diagram-type identifier from the fence's
  first non-blank line and surfaces it as an auto-keyword (see below).

- **Dictionary-free keyword extraction**: every block whose source does not
  declare `keywords:` gets a viewer-side auto-extracted top-N keyword chip
  row. The algorithm is N-gram (CJK 2–8 chars + ASCII tokens) + PMI cohesion
  (`min_pmi ≥ 1.0`) + Left/Right Shannon entropy (`≥ 0.4`) + frequency ≥ 2,
  scored `freq × min-PMI × min(L, R)-entropy`, with substring suppression.
  Author-declared `keywords:a,b,c` always wins; auto suggestions only fill
  gaps. Structural tags are prepended automatically: blocks containing
  ` ```svg ` get `svg`; blocks containing ` ```mermaid ` get `mermaid` plus
  the diagram type (`sequenceDiagram` / `flowchart` / `classDiagram` /
  `gantt` / `graph` / ...).

- **Authoring guidance for keywords**:
  - In general, leave `keywords:` off. The viewer will show auto suggestions
    in a dashed-border chip. The playground has a "寫入 keywords" button
    that persists the suggestions back into source after confirmation.
  - Declare `keywords:` explicitly when (a) the auto suggestions are
    misleading (block uses unusual vocabulary that statistical signal misses),
    (b) downstream agents query by keyword and the author needs precise
    control, or (c) the document is single-block / short and the corpus
    statistics are too thin for the extractor.
  - Do NOT manually duplicate `svg` / `mermaid` / `<diagram-type>` in
    `keywords:` when those tags would be auto-attached anyway. Trust the
    viewer's structural-tag injection.

These features assume the viewer at `markdown_plus_repo/public/lib/` (or its
inlined copy in `playground.html`). Other viewers may not have them; treat
them as graceful enhancement, not a hard requirement.
</viewer_features>

<references>
Load on demand based on the task:

- `references/quality_checklist.md` — readiness gate. Run this every time before declaring done.
- `references/what-is-markdown-plus.md` — concept, why, spirit, design principles, empirical token-cost evidence vs Markdown / HTML. Load when the user asks "what is Markdown+", "why this format", or wants justification.
- `references/syntax-reference.md` — full block header grammar, nesting rules, caption conventions, fence usage. Load when the user asks how to write a specific construct.
- `references/metadata-vocabulary.md` — controlled vocabulary for `type`, `status`, `trend`, `visibility`, plus tag namespacing. Load whenever assigning metadata.
- `references/rewriting-playbook.md` — concrete procedures for `markdown → markdown+` and `html → markdown+`. Load whenever the input type is `rewrite_markdown` or `rewrite_html`.
- `references/code-fence-preservation.md` — hard rule: code fences, ASCII trees, aligned art must be preserved verbatim during rewrite. Load when rewriting input that contains code fences or alignment-sensitive content.
- `references/worked-examples.md` — before/after pairs and bad/good pairs. Load when an example would clarify the requested construct.
</references>

<testing>
Eval assets for triggering / functional / edge-abuse testing:
- `assets/evals/evals.json` — trigger should/shouldnot, near-miss, multilingual; functional Given/When/Then; edge & abuse cases.
- `assets/evals/regression_gates.json` — minimum pass-rate delta, time/token caps, must-pass test IDs for release.

Run via `skill-creator-advanced`:
```bash
python <skill-creator-advanced>/scripts/run_eval.py --eval-set markdown-plus-author/assets/evals/evals.json --skill-path markdown-plus-author --model <model-id>
python <skill-creator-advanced>/scripts/prepare_eval_workspace.py markdown-plus-author
python <skill-creator-advanced>/scripts/check_regression_gates.py
```
</testing>

<empirical_evidence>
A 100-call benchmark (5 use cases × 5 docs × 4 formats, gpt-5.5) measured output cost of converting plain Markdown into each target format. Use these numbers when justifying Markdown+ to a skeptical reader; they directly contradict the common claim that "HTML costs only a few extra tokens".

| Format        | Output tokens vs Markdown | Rewrite time vs Markdown |
|---------------|---------------------------|--------------------------|
| Markdown      | 1.00× (baseline)          | 1.00× (baseline)         |
| **Markdown+** | **1.46×**                 | **0.75×** (faster than generating Markdown from scratch) |
| Medium HTML   | 1.70×                     | 1.02×                    |
| Heavy HTML    | **2.37×**                 | 1.49×                    |

Stability across use cases: Markdown+ ratio is tight (1.43×–1.50×); Heavy HTML ratio swings 1.87× – 3.35× depending on scenario (Tutorial is the worst case for Heavy HTML). Full table per use case lives in `references/what-is-markdown-plus.md`.

Reference implementation (validator / viewer / rewriter / playground) lives at `D:\PycharmProjects\TokenSaving\markdown-plus-ecosystem\` for the host that maintains this skill. Other hosts should consult their own copy or the public release.
</empirical_evidence>

<model_notes>
Reasoning models: keep prose companions concise (1–2 sentences). The model often over-explains figures; constrain it via the output contract.

GPT-class models: be explicit about every step. The Step 1–7 numbering matters; condensing into fewer steps causes step omission.

For any model: never let the model invent new `type:` values without an `x-` prefix and a documented fallback projection. Closed vocabulary is the routing signal for viewers.
</model_notes>

<examples>
Minimal worked example — plain Markdown → Markdown+:

Input:
```markdown
## Current auth state
We use Auth v2 today. Gateway handles refresh.

## History
Auth v1 stored tokens in cookies. Deprecated in 2026-02.
```

Output:
```markdown
# Auth Service Notes

目前狀態與棄用歷史。

- **#current-state** `type:state` `status:active` `updated:2026-05-13` `tags:[auth,gateway]`
  We use Auth v2 today. Gateway handles refresh.

- **#auth-v1** `type:history` `status:deprecated` `superseded-by:current-state` `visibility:collapsed` `tags:[auth,archive]`
  Auth v1 stored tokens in cookies. Deprecated 2026-02.
```

For richer before/after pairs (HTML → Markdown+, dashboard with KPI grid, dialogue, variants), see `references/worked-examples.md`.
</examples>
