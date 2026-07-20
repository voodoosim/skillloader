# SkillLoader Product and Delivery Plan

## Product thesis

SkillLoader keeps a large skill catalog outside an AI model's steady-state
context. The model sees two small MCP tools, searches bounded metadata, and
loads only the selected skill body.

The product is valuable only if it proves all three outcomes together:

1. lower skill-catalog context overhead;
2. routing and loaded-content behavior at least as reliable as the current
   Python loader; and
3. installation as one local binary without Docker.

Caching is a latency feature. It is not counted as a token-saving feature.

## MVP objective

Deliver one Go binary that serves the current 82-skill catalog over local stdio
MCP using only `search_skills` and `load_skill`, works through one verified Codex
bootstrap, matches frozen Python-loader behavior, and produces reproducible
token, quality, and latency evidence.

## MVP scope

### Included

- Trusted local catalog roots
- Existing `SKILL.md` metadata and complete-body loading
- Deterministic, bounded metadata search
- Exact load by logical skill name
- In-memory metadata and parsed-document cache with invalidation
- Two model-visible MCP tools over stdio
- `skillloader list --json` and `skillloader doctor --json` for operators
- One Codex bootstrap integration
- Python parity fixtures and reproducible benchmarks
- One-binary installation and smoke test outside the repository

### Deferred until the MVP gates pass

- Streamable HTTP and remote access
- Docker image
- Claude, OpenCode, and other client adapters
- Web UI, hosted service, marketplace, and automatic skill downloads
- Embeddings, vector databases, and semantic reranking
- Cloud synchronization, accounts, telemetry, and billing

## Fixed design decisions

| Surface | MVP decision | Reason |
|---|---|---|
| Runtime | Go single binary | Local distribution without Python or Node runtime |
| Transport | stdio only | Smallest local trust and deployment boundary |
| MCP surface | `search_skills`, `load_skill` | Only model-required operations consume tool-schema context |
| Operator surface | CLI `list`, `doctor` | Diagnostics do not belong in model context |
| Identity | Logical skill name | Portable and prevents caller-controlled paths |
| Search | Current deterministic ranking first | Establish parity before algorithm changes |
| Cache | In-process metadata and parsed documents | Improve repeat latency without changing protocol output |
| Claims | Benchmark-backed only | Prevent token and compatibility overstatement |

## Acceptance gates

### Gate 0 — Repository readiness

- [x] Create the correctly spelled project and initialize local Git on `main`.
- [x] Record architecture, protocol, benchmark, and contribution rules.
- [ ] Confirm the GitHub owner and Go module path.
- [ ] Select an open-source license.
- [ ] Resolve or explicitly accept the observed `GOPATH == GOROOT` warning.
- [x] Create the initial documentation commit before implementation changes.

Exit evidence: clean documentation checks, selected module path and license, and
a recorded decision on the Go environment warning.

### Gate 1 — Core parity and safety

- [ ] Initialize `go.mod` and pin the official Go MCP SDK.
- [ ] Add sanitized catalog and query fixtures from the Python loader.
- [ ] Parse and validate every skill in the frozen 82-skill catalog.
- [ ] Match exact-load content and metadata for all 82 frozen skills.
- [ ] Match Python search ordering for the frozen parity query set.
- [ ] Reject missing names, duplicate names, root escapes, and symlink escapes.
- [ ] Prove cache hit, update, removal, and invalidation behavior with tests.

Exit evidence: exact test commands pass, `doctor` reports the expected frozen
catalog counts, and no parity or path-safety case remains unresolved.

### Gate 2 — Minimal product path

- [ ] Expose only `search_skills` and `load_skill` through stdio MCP.
- [ ] Add stable structured outputs and redacted error envelopes.
- [ ] Implement CLI `list --json`, `doctor --json`, and useful `--help` output.
- [ ] Build the binary and smoke-test it from outside the repository.
- [ ] Verify one Codex bootstrap invokes search, loads one skill, and applies the
  complete returned document on the labeled integration tasks.

Exit evidence: the built binary completes protocol and external-directory smoke
tests without Python, Node, Docker, or repository-relative paths.

### Gate 3 — Product evidence

- [ ] Compare eager registration and SkillLoader under identical client, model,
  task, catalog, and sampling conditions.
- [ ] Report steady-state catalog overhead, routed-task overhead, and total input
  tokens separately.
- [ ] Target at least 90% lower skill-catalog overhead; always publish the measured
  result, but do not market a 90% claim if the result does not reach it.
- [ ] Match or exceed Python-baseline top-1, top-5, incorrect-load, and no-load
  results on the labeled task set.
- [ ] Run at least 100 cold and 100 warm search/load iterations and report p50 and
  p95 latency.
- [ ] Require warm p95 search and load latency to beat the current Python
  subprocess baseline on the same machine.
- [ ] Commit machine-readable benchmark inputs and results.

Exit evidence: `docs/BENCHMARK.md` can reproduce every public token, quality, and
latency statement from committed result artifacts.

### Gate 4 — First public release

- [ ] Add reproducible release builds for explicitly tested platforms.
- [ ] Document installation, configuration, upgrade, and rollback.
- [ ] Complete a clean-room install and Codex integration test from the release
  artifact.
- [ ] Add security reporting guidance and enable private vulnerability reports.
- [ ] Publish a release only with measured claims and an explicit compatibility
  matrix.

Exit evidence: a new machine or clean environment can install one artifact and
complete the documented Codex workflow.

## Stop conditions

Stop expanding scope and revisit the design when any condition occurs:

- Codex does not reliably apply the loaded skill body through the bootstrap.
- The two-tool schema plus bootstrap fails to reduce catalog overhead.
- Search or load parity cannot be reproduced from frozen fixtures.
- Path containment depends on trusting caller-provided paths.
- The benchmark cannot separate catalog-only savings from total request tokens.
- HTTP, Docker, a second client, or semantic search is requested before Gate 3
  evidence exists.

## Post-MVP order

Only after Gates 0–3 pass:

1. verify a second MCP client with its own bootstrap and compatibility notes;
2. design authenticated Streamable HTTP transport;
3. add an optional Docker image;
4. evaluate semantic ranking only against the labeled routing baseline; and
5. consider registry, marketplace, UI, or hosted features from observed demand.

## Open decisions

| Decision | Required before | Current state |
|---|---|---|
| GitHub owner and Go module path | Gate 1 | User confirmation required |
| License | Gate 1 | User confirmation required |
| Go environment warning | Gate 1 | Effective `GOPATH` and `GOROOT` are identical |
| Catalog root configuration format | Gate 2 | Design after core types exist |
| Search result maximum | Gate 2 | Benchmark and context measurement required |
| Cache size and eviction | Gate 3 | Benchmark required |
| Second supported client | Post-MVP | Choose after Codex evidence |
| HTTP authentication and listen policy | Post-MVP | No design before local MVP evidence |
