# Benchmark Specification

## Purpose

Measure whether SkillLoader reduces skill-related context overhead without
damaging routing quality or task completion. Measure cache performance
separately so latency improvements are not mislabeled as token savings.

No positive token-reduction percentage is currently verified. The recorded,
currently uncommitted live Codex small-catalog result below measured an increase
in total input.

## Claims under test

1. Catalog size can grow without placing every skill description in steady-state
   model context.
2. A routed task can expose a bounded match set and one selected skill body.
3. Skill-catalog overhead and total request tokens can be measured separately
   under documented catalog sizes and client configurations.
4. Cold and warm load latency can be compared without treating cache behavior
   as token savings.

## Compared configurations

### Eager baseline

Register the complete test catalog directly in the client's ordinary skill
discovery surface. Capture the exact model-visible prompt or client-reported
input-token count before the task answer begins.

### SkillLoader

Expose only the client bootstrap and SkillLoader MCP tool definitions initially.
For each task, capture the search call, bounded results, selected skill body, and
all client-reported input tokens.

The model, client version, system instructions, user task, catalog contents,
selected skill, and sampling settings must match between configurations.

## Catalog sets

- A recorded snapshot of the real catalog; its count is an observation, not a
  parity target
- A versioned medium fixture catalog
- A versioned large fixture catalog

Fixture creation must preserve realistic description and body-size distributions.
Synthetic duplication must be labeled and must not be used for routing-quality
claims.

## Task set

Use a versioned, labeled suite containing:

- exact-name requests;
- tag and synonym requests;
- Korean and English requests;
- ambiguous requests;
- requests that should load no specialist skill;
- requests requiring one specialist skill;
- requests requiring a separate safety or verification gate.

Each task records the expected top match, exact required skill names, allowed
alternatives, and whether no load is correct.

The committed task fixture is `bench/tasks/task-fixture-v1.json`. It targets the
parity test catalog (`testdata/parity/`) and covers all required categories with
12 tasks. Run the parity test to verify search ranking correctness against this
catalog, then use the same tasks for eager-vs-SkillLoader comparison with a live
client.

## Metrics

### Token metrics

- Steady-state skill overhead before any tool call
- Search-result input tokens
- Loaded-skill input tokens
- Total input tokens for the completed task
- Catalog-overhead reduction percentage
- Total-request reduction percentage

Report the two reduction percentages separately:

```text
reduction = 1 - (SkillLoader measured tokens / eager measured tokens)
```

Token-cache measurements must include a cold request and repeated warm requests
in the same client session. A warm cache result is valid only when the client
reuses the prior `query_hash` or `content_sha256` and the MCP response omits the
repeated payload. Server-side file-cache hits alone are latency measurements,
not token savings.

Use a client-reported or model-provider token count when available. If an offline
tokenizer is used, record its exact name and version and label the result as an
estimate.

### Quality metrics

- Top-1 routing accuracy
- Top-5 routing recall
- Incorrect-load rate
- No-load accuracy
- Task success using the selected skill

### Performance metrics

- Cold start duration
- Cold and warm search latency: p50 and p95
- Cold and warm load latency: p50 and p95
- Catalog indexing duration and memory use
- Cache hit and invalidation behavior

## Evidence format

Store benchmark artifacts under a future versioned `bench/results/` directory:

```text
bench/results/<date>-<client>-<catalog>/
  environment.json
  catalog.json
  tasks.jsonl
  eager.jsonl
  skillloader.jsonl
  summary.json
```

Redact credentials and user data before committing results.

## Core timing evidence

The opt-in `TestBenchmarkEvidence` test measures direct Go catalog-core search
and load calls over a synthetic 100-skill catalog. It reports p50, p95, and mean
nanoseconds for 50 iterations per operation:

```bash
SKILLLOADER_BENCHMARK=1 \
SKILLLOADER_BENCHMARK_OUTPUT=/tmp/skillloader-benchmark-evidence.json \
go test -run TestBenchmarkEvidence -count=1 -v .
```

The recorded result is `bench/results/2026-07-20-go1.26.5-fixture100.json`.
It is core-process timing only: it does not measure MCP transport overhead,
Codex client behavior, token counts, or a real user catalog.

### Currently recorded evidence (2026-07-20, Go 1.26.5, fixture-100)

| Mode | Operation | p50    | p95    | Mean   |
| ---- | --------- | ------ | ------ | ------ |
| Cold | search    | 4.47ms | 5.49ms | 4.52ms |
| Cold | load      | 34.7µs | 72.9µs | 42.1µs |
| Warm | search    | 29.3µs | 52.9µs | 36.1µs |
| Warm | load      | 19.0µs | 32.3µs | 28.9µs |

The internal Go `testing.B` benchmarks (`BenchmarkColdBuild`, `BenchmarkWarmSnapshot`)
measure catalog-index build and snapshot-load over a 50-skill catalog:

```bash
go test -bench=Snapshot -benchmem -count=5
```

These exclude disk I/O by resetting the timer, and exclude binary-startup
overhead. For binary-level cold-start and warm-start, smoke-test the built
binary outside the repository:

```bash
go build -o /tmp/skillloader .
/tmp/skillloader doctor --json    # cold start: catalog build + parse
/tmp/skillloader doctor --json    # warm start: snapshot cache hit
```

## Live Codex routing evidence

The generated result directory
`bench/results/2026-07-21-codex-0.144.6-gate6-isolated/` contains 12 paired live runs on
Codex CLI `0.144.6`, model `gpt-5.6-sol`, and the 10-skill synthetic parity
catalog in temporary isolated `HOME` and `CODEX_HOME` directories. Run or
rescore it with `scripts/run_gate6_codex.py` as documented in
`docs/PRODUCT_EVIDENCE.md`.

| Metric                                 |   Eager | SkillLoader |
| -------------------------------------- | ------: | ----------: |
| Routing-fixture success                |   10/12 |       11/12 |
| Final selection top-1                  |    9/10 |        9/10 |
| Raw search top-1                       |     n/a |        8/10 |
| Raw search top-5 recall                |     n/a |        9/10 |
| No-load accuracy                       |     1/2 |         2/2 |
| Incorrect-load runs                    |    2/12 |        0/12 |
| Total input tokens, client-reported    | 152,353 |     522,331 |
| Uncached input tokens, client-reported | 140,321 |     155,483 |
| Total wall time                        | 87.149s |    194.094s |

The exact small-catalog initial static estimate was 711 eager tokens versus 619
SkillLoader tokens, a 12.94% reduction. Despite that, SkillLoader required
extra model turns for search and load. Its client-reported total input increased
242.84%, uncached input increased 10.81%, and wall time increased 122.72%.

The earlier `bench/results/2026-07-21-codex-0.144.6-gate6/` comparison is
superseded because host-level `AGENTS.md` instructions entered its effective
prompts. It remains historical execution evidence, not product-comparison
evidence.

This is a routing and selected-skill final-instruction extraction fixture, not a
task completion benchmark. It uses one run per task and does not establish a
large-catalog break-even point or a positive product token claim.

After execution, review found that the regression query requested testing but
the scoring fixture also required the unrelated release-notes skill. The
scoring-only oracle was corrected to require `test-designer`; the recorded
query, effective prompt, model output, usage, and duration were not changed.

## Live Claude Code routing evidence

The generated result directory
`bench/results/2026-07-25-claude-code-2.1.212-gate6-isolated/` contains 12
paired live runs on Claude Code CLI `2.1.212`, model `sonnet` (`claude-sonnet-5`),
and the same 10-skill synthetic parity catalog used for the Codex comparison
above. Run it with `scripts/run_gate6_claude_code.py`; there is no rescore
mode for this runner.

Isolation differs from the Codex runner because Claude Code exposes no
`--ignore-user-config`/`--ephemeral`/isolated-home equivalent that also
preserves subscription auth: `--bare` was tested and rejected because it also
skips keychain reads. The accepted isolation is `--setting-sources ""`
(skips project/user `settings.json`, hooks, and CLAUDE.md-driven system-prompt
assembly) plus `--disable-slash-commands` (skips all locally installed
skills) plus `--strict-mcp-config` (only the MCP server passed via
`--mcp-config` is registered). This was verified empirically per run by
inspecting the recorded `system_init` event's `tools`, `skills`, and
`mcp_servers` fields (`skills: []`, only the `skillloader` MCP server
connected) and confirming no `SessionStart` hook output appears in any
transcript; it was not verified against every possible local hook/plugin
combination.

Claude Code 2.1.212 defers MCP tool schemas behind a built-in `ToolSearch`
tool: the model must call `ToolSearch` to resolve `search_skills` or
`load_skill` before it can invoke either one. This has no Codex analogue,
costs an extra model turn per resolved tool name, and is recorded separately
as `toolsearch_call_count_total` rather than folded into the search/load
scores below.

| Metric                                                                     |   Eager | SkillLoader |
| -------------------------------------------------------------------------- | ------: | ----------: |
| Routing-fixture success                                                    |   12/12 |       10/12 |
| Final selection top-1                                                      |   10/10 |        8/10 |
| Raw search top-1                                                           |     n/a |        8/10 |
| Raw search top-5 recall                                                    |     n/a |        9/10 |
| No-load accuracy                                                           |     2/2 |         2/2 |
| Incorrect-load runs                                                        |    0/12 |        0/12 |
| ToolSearch calls (deferred-tool overhead)                                  |       0 |          17 |
| Total prompt tokens, client-reported (input + cache creation + cache read) | 189,426 |     700,784 |
| Total cost, client-reported                                                | $0.2004 |     $0.5028 |
| Total wall time                                                            | 70.478s |    150.664s |

For this small catalog, SkillLoader used 3.70 times the total prompt tokens
and 2.51 times the client-reported cost of eager mode. Expressed through the
benchmark's reduction formula, the results are `-269.95%` total prompt-token
reduction and `-150.95%` cost reduction; these negative values mean
increases. This matches the same small-catalog direction observed against
Codex above, with the deferred-tool `ToolSearch` round trip as an additional,
Claude-Code-specific cost layer.

Anthropic's usage accounting (`input_tokens` / `cache_creation_input_tokens`
/ `cache_read_input_tokens` / `output_tokens`) is not the same shape as
Codex's (`input_tokens` / `cached_input_tokens` / `output_tokens` /
`reasoning_output_tokens`). Do not compare totals between the Codex and
Claude Code result directories as if they used one accounting model; each
client's numbers are only comparable against its own eager-mode run.

Both quality failures were Korean-language queries:

1. For `한글 라우팅 검색`, SkillLoader's search correctly ranked
   `korean-router` first (raw top-1 and top-5 recall both correct), but the
   model declined to load it, reasoning that a skill whose own description is
   about routing/searching would be "circular" for a query with no concrete
   task. This is a model reasoning outcome on a self-referential fixture
   skill, not a SkillLoader search defect.
2. For `릴리스 노트 작성해줘` (Korean for "write release notes"), SkillLoader's
   search returned zero matches for the English-only `release-notes` skill
   (description "Write release changelogs and documentation.", tags
   `release, changelog, documentation`). SkillLoader's ranking is lexical, not
   semantic; it has no mechanism to bridge a Korean phonetic loanword
   (`릴리스` / `노트`) to English skill metadata. This is the same gap noted
   in the Codex evidence's "Observed quality failures" for the same query,
   confirming it is a search-ranking limitation, not a client-specific
   artifact.

## Acceptance rule

The README may publish a numerical skill-catalog overhead claim only after a
committed result states the client, catalog size, task set, and measurement
method next to the result. Total-token savings must never be substituted with
catalog-only savings.
