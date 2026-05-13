# Benchmark Results — Token Cost & Rewrite Time

100 LLM calls (gpt-5.5, reasoning effort `none`) across 5 use cases × 5 documents × 4 output formats. The Markdown+ phase was re-run with the new bullet-list syntax (no `:::block`) and saved separately for honest comparison.

## TL;DR

| Format        | Output tokens vs Markdown | Rewrite time vs Markdown | Verdict |
|---------------|---------------------------|--------------------------|---------|
| Markdown      | 1.00× (baseline,12,428 mean) | 1.00× (182s mean)        | — |
| **Markdown+** | **1.46×** (18,102 mean)   | **0.75×** (137s mean)    | sweet spot |
| Medium HTML   | 1.70× (21,083 mean)       | 1.02× (187s mean)        | tag noise without AI win |
| Heavy HTML    | **2.37×** (29,427 mean)   | 1.49× (272s mean)        | expensive AND slow |

**The "HTML costs only a few extra tokens" claim does not hold up:** Heavy HTML uses 137% more tokens than plain Markdown, and Medium HTML uses 70% more.

Markdown+ is a stable middle ground that adds semantic structure without exploding the token budget — and it's actually **faster** than generating Markdown from scratch (because the rewrite has the source as reference).

## Per use case — tokens

| Use Case | n | Mean MD | Mean MD+ | Mean Medium HTML | Mean Heavy HTML | MD+/MD | Medium/MD | Heavy/MD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| API Reference | 5 | 12,060 | 17,439 | 19,823 | 28,419 | 1.45× | 1.64× | 2.36× |
| Meeting Notes / Decision Records | 5 | 11,667 | 16,680 | 20,412 | 29,937 | 1.43× | 1.75× | 2.57× |
| Research / Investigation Report | 5 | 11,494 | 16,468 | 21,441 | 25,145 | 1.43× | 1.87× | 2.19× |
| Technical Spec / PRD | 5 | 17,984 | 26,537 | 29,540 | 33,654 | 1.48× | 1.64× | 1.87× |
| Tutorial / How-to | 5 | 8,937 | 13,387 | 14,200 | 29,979 | 1.50× | 1.59× | 3.35× |
| **All** | 25 | **12,428** | **18,102** | **21,083** | **29,427** | **1.46×** | **1.70×** | **2.37×** |

## Per use case — rewrite time

| Use Case | n | Mean MD (s) | Mean MD+ (s) | Mean Medium HTML (s) | Mean Heavy HTML (s) | MD+/MD | Heavy/MD |
|---|---:|---:|---:|---:|---:|---:|---:|
| API Reference | 5 | 149.2 | 137.0 | 177.7 | 246.2 | 0.92× | 1.65× |
| Meeting Notes / Decision Records | 5 | 199.4 | 125.5 | 170.7 | 263.5 | 0.63× | 1.32× |
| Research / Investigation Report | 5 | 175.7 | 125.2 | 201.9 | 281.0 | 0.71× | 1.60× |
| Technical Spec / PRD | 5 | 277.5 | 195.7 | 265.2 | 301.6 | 0.71× | 1.09× |
| Tutorial / How-to | 5 | 108.6 | 101.3 | 116.8 | 266.6 | 0.93× | 2.46× |
| **All** | 25 | **182.1** | **136.9** | **186.5** | **271.8** | **0.75×** | **1.49×** |

## Observations

- **Markdown+ ratio is tight across scenarios** (1.43×–1.50×). Easy to budget.
- **Heavy HTML swings wildly** (1.87× for Tech Spec, **3.35× for Tutorial**). Tutorials need navbar / step navigators / interactive containers, so HTML inflates dramatically.
- **Markdown+ rewrite is faster than Markdown generation** because the source is already on hand. The LLM doesn't have to think from scratch.
- v2 vs v1 Markdown+: v2 uses +28.7% tokens but is **−26.9% faster**. New SKILL requires richer metadata + prose companions (token cost), but bullet-list + inline-code is more natural for the LLM (time saving).

## Methodology

- Model: `gpt-5.5` via OpenAI Responses API (`reasoning.effort: none`)
- Generation phase: from topic only (no source markdown)
- Rewrite phases: source markdown + prompt template for target format
- Strictly sequential execution (no parallel calls), 1 s pause between calls
- Time = wall-clock `perf_counter()` from request submission to last stream event
- Token = `usage.output_tokens` only (input tokens excluded; reflects "what you pay to produce the format")

Raw data: see `benchmark/results/metrics.jsonl` and `metrics_v2.jsonl` in the parent project (`TokenSaving/`).
