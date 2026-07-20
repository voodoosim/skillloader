# Benchmark Specification

## Purpose

Measure whether SkillLoader reduces skill-related context overhead without
damaging routing quality or task completion. Measure cache performance
separately so latency improvements are not mislabeled as token savings.

No token-reduction percentage is currently verified.

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

Each task records the expected top match, allowed alternatives, and whether no
load is correct.

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

| Mode | Operation | p50 | p95 | Mean |
|------|-----------|-----|-----|------|
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

## Acceptance rule

The README may publish a numerical skill-catalog overhead claim only after a
committed result states the client, catalog size, task set, and measurement
method next to the result. Total-token savings must never be substituted with
catalog-only savings.
