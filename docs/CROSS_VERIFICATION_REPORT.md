# SkillLoader Cross-Verification Report

**Date**: 2026-07-20  
**Target SHA**: `86e303ed1e85cd12d8096ecf1013c47bc038f3b5`  
**Branch**: `main`  
**Reviewer**: Claude (opencode) — independent from Codex (gpt-5.6-luna)  
**Scope**: Full-stack independent cross-verification of the entire repository

---

## 1. Verification Suite Pass Rates

| Command | Result |
|---|---|
| `go vet ./...` | PASS |
| `go test -count=1 ./...` | PASS (56 test functions) |
| `go test -race -count=1 ./...` | PASS |
| `go build ./...` | PASS |
| `gofmt -d *.go` | CLEAN |
| `scripts/smoke-test.sh` | PASS (6 steps) |
| `go test -run=Benchmark -bench=. -count=1` | PASS (cold/warm) |
| `go run ./.../govulncheck@latest ./...` | 0 vulnerabilities |
| `git diff --check HEAD~3..HEAD` | CLEAN |

**All tests pass with no exceptions.**

---

## 2. Architecture Tier Review

### 2.1 Loader (3-layer containment)

`catalog.go:175-218` — `readTrustedFile(roots, path)`

- Layer 1: `filepath.Rel` — reject paths not under a configured root
- Layer 2: `filepath.EvalSymlinks` — resolve symlinks on both root AND path, re-check containment  
- Layer 3: `os.OpenRoot(absRoot).ReadFile(rel)` — OS-enforced sandboxed read

**Assessment**: Robust against traversal attacks. The symlink escape fix (994c15d critical bug) is properly verified.

### 2.2 Snapshot (4-layer invalidation)

`snapshot.go:80-115` — `loadSnapshot(roots)`

- Layer 1: RootsHash — roots changed → invalidate
- Layer 2: dirFingerprint — new or deleted SKILL.md → invalidate
- Layer 3: mtime mismatch on any cached entry → invalidate
- Layer 4: sha256 checksum mismatch (`snapshot_test.go:103`) — same mtime, changed content → invalidate

**Assessment**: Comprehensive invalidation. The stale-snapshot-on-same-mtime bug (994c15d critical bug) is properly fixed.

### 2.3 Search Engine (8-layer pipeline)

`search.go:30-90`

1. Query tokenization (compound + sub-token)
2. Tag matching (weight ×8 per match)
3. Name matching (exact ×100, substring ×20)
4. Description matching (weight ×5 per match)
5. Score aggregation + deterministic sort
6. Deduplication by logical name
7. Safety filter (reject empty name/path + score ≤ 0)
8. Result limit (1-10, default 5)

**Assessment**: Deterministic, rank-stable, zero-score filter prevents noise results. Ambig rejection policy matches AGENTS.md L42.

### 2.4 MCP Contract

`main.go:50-114` — Two tools with structured outputs:

| Tool | Input | Output |
|---|---|---|
| `search_skills` | `query` (string), `limit` (*int, omitempty) | `SearchOutput` (matches + catalog_revision) |
| `load_skill` | `name` (string, exact match) | `LoadOutput` (skill + catalog_revision) |

- `limit` is pointer-typed — correctly optional (89e2538 fix)
- Errors use `SkillError` with machine-readable codes
- MCP error messages never leak trusted root paths (mcp_test.go verified)
- Full in-memory integration test in `mcp_test.go`

### 2.5 Cache

`cache.go`

- Caller-provided checksum — no double I/O (REVIEW3 fix)
- Document invalidation on checksum mismatch
- Index storage with aggregate hash
- Thread-safe (sync.RWMutex)

### 2.6 Catalog & YAML

`catalog.go` — `yaml.v3` parser with:
- `normalizeYAMLString()` — coerce `!!seq` lists into `["tag1, tag2"]` (21a8279 fix)
- `normalizeYAMLTags()` — accept `#tag` and bare-tag formats
- `os.OpenRoot` for FS walks — no path traversal during discovery
- Redacted error messages — no root paths in error strings

### 2.7 Parity Fixtures

`parity_test.go`, `testdata/parity/`, `scripts/verify_parity.py`

| Metric | Result |
|---|---|
| Catalog match (10 skills) | 10/10 |
| Top-1 search match (10 queries) | 9/10 |
| Exact ranking match (10 queries) | 9/10 |
| Load content + SHA256 match (10 skills) | 10/10 |
| verify_parity.py (Python side) | PASS |

**mcp-contract failure** (known, documented in PARITY.md):  
Go's Layer 4 description matching scores `api-guardian` (description "contracts" ⊃ token "contract") at 5 points. Python matches on name+tag only. This is a design policy decision:
- Remove Layer 4 → exact parity with Python  
- Keep Layer 4 → Go is strictly better at recall (Gate 1 exit decision)

### 2.8 Integration Harness

`integration_test.go` — 5 Codex-pattern scenarios:
- Search→load→verify (description query, tag query, name query, mixed query)
- Search→load→verify (Korean query "한글 라우팅")
- Consistency: same query returns same catalog_revision
- Error propagation: missing skill returns SKILL_NOT_FOUND
- Result variants: limit=2, then limit=5 returns superset

`scripts/smoke-test.sh` — automated build+doctor+list+help+stdio steps.

---

## 3. Performance

Benchmark results at a093b89 (50-skill catalog, i9-14900KF):

```
BenchmarkColdBuild-24        656  1.80ms/op   719 KB/op   7546 allocs/op
BenchmarkWarmSnapshot-24     588  2.01ms/op   472 KB/op   6279 allocs/op
```

| Metric | Cold (no snapshot) | Warm (snapshot) |
|---|---|---|
| BuildIndex + saveSnapshot | 1.80 ms | — |
| loadSnapshot (gob decode + mtime verify) | — | 2.01 ms |

Cold and warm are similar because `loadSnapshot` must `stat()` every file for mtime verification — O(n) syscalls dominate at this catalog size. Snapshot eliminates YAML parsing cost but preserves correctness through comprehensive invalidation.

---

## 4. Known Issues (after fix)

### M2 — Snapshot checksum reads every file (DEFERRED optimization)
`snapshot.go` re-reads and hashes every discovered file on warm validation. This preserves correctness when content changes without an mtime change, but makes warm validation O(n) in file bytes. Keep checksum validation until a safe metadata strategy is demonstrated by benchmark.

### L1 — HANDOFF.md HEAD reference (resolved)
The handoff now records the current report commit `0262c79`; future commits must update this observed-state line.

---

## 5. Gate Status

| Gate | Status | Blockers |
|---|---|---|
| Gate 0 (baseline) | DONE | Module path set, MIT license, Go 1.26.5, MCP SDK v1.6.1 |
| Gate 1 (core parity) | 90% | mcp-contract design decision (Layer 4 keep/remove) |
| Gate 2 (product path) | DONE | MCP tools, structured output, CLI, smoke, integration |
| Gate 3 (benchmark evidence) | DONE | Benchmark data recorded, 0% token reduction claim until live Codex |

---

## 6. Final Assessment

**Verdict: MERGE SAFE — live-client validation and Layer 4 policy decision remain pending**

Strengths:
- All security-critical bugs from cross-review resolved
- Three independent verification passes (Codex review, parity fixtures, cross-verification)
- Comprehensive test coverage (unit + integration + MCP + parity + smoke + benchmark)
- Performance baseline recorded (benchmark_data.txt)

One open decision:
- `docs/PARITY.md` — keep or remove search Layer 4 (description matching)

No blocking issues. Ready for Gate 3 live Codex integration.
