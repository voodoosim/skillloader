# SkillLoader Handoff

Last verified: 2026-07-20 KST

This file records the current branch state. Historical rationale and
remaining gates belong in `plan.md` and `CODEX_PLAN_BASELINE.md`.

## Observed state

| Surface | State | Evidence |
|---|---|---|
| Project root | `/home/vodo/workspace/projects/skillloader` | `git rev-parse --show-toplevel` |
| Git | Branch `fix/review-findings`, review base `3d4caa0`, no remote configured | `git branch --show-current`, `git log --oneline`, `git remote` |
| Runtime | Go `1.25.0` on `linux/amd64` | `go version` |
| Go environment | Effective `GOPATH` and `GOROOT` are both `/home/vodo/go`; every Go command emits a warning | `go env GOPATH GOROOT` |
| Implementation | Local Go prototype with catalog, YAML frontmatter parsing, search, trusted-root load, cache, two typed MCP tools, and operator CLI | source tree and tests |
| MCP | In-memory integration test verifies exactly `search_skills` and `load_skill`, output schemas, structured results, TextContent compatibility, and redacted errors | `go test -count=1 ./...` |
| CLI | `list`, `doctor`, `help`, `--help`, and `-h`; help exits 0 | unit test and outside-repository smoke |
| Local catalog | 132 valid parsed skills, 6 errors, 132 missing-tag warnings | `go run . doctor --json` |
| Module | Placeholder local module path `skillloader`; MCP SDK `v1.2.0`; YAML `v3.0.4` | `go.mod` |
| License | Not selected | repository inventory |

The six current doctor errors are five invalid frontmatter diagnostics (four
documents lack an opening YAML delimiter and one has a sequence-valued
description) plus one duplicate logical-name diagnostic. `skill_count`,
`error_count`, and `warning_count` are independent diagnostic dimensions.

## Decisions applied in this branch

- Treat the product as a local skill catalog loader/server, not an operating system.
- Treat missing tags as valid with a doctor warning.
- Parse YAML list tags and multiline descriptions; reject documents without YAML
  frontmatter in the MVP.
- Keep search weights deterministic but provisional until fixture-based tuning.
- Return no results for zero-score queries.
- Read and hash current file bytes on every load; use the document cache only
  after checksum verification. Cache latency remains unmeasured.
- Enforce trusted-root containment with `os.Root` and reject direct and symlink
  escapes.
- Return typed MCP structured output with `catalog_revision` and stable redacted
  application errors.
- Require server restart for catalog/search metadata refresh; hot reload is not
  implemented.
- Interpret `SKILLLOADER_ROOTS` as comma-separated literal paths with whitespace
  trimming only. Relative paths use the process working directory; quote, tilde,
  and glob expansion are unsupported.
- Keep search tokenization limited to English letters, digits, Hangul, and
  hyphens. Japanese/Chinese expansion was removed as out of scope.

## Verification completed in this working tree

```text
gofmt -w *.go                              completed
go test -count=1 ./...                     pass (37 top-level test functions)
go test -race -count=1 ./...               pass
go vet ./...                               pass
go build ./...                             pass
go run . doctor --json                     132 skills / 6 errors / 132 warnings
outside-repository binary help/list/doctor  pass
outside-repository stdio EOF smoke          pass, exit 0
skill_loader.py doctor                      82 skills / 0 errors
```

All Go commands still emit the observed `GOPATH == GOROOT` warning.

## Exact unverified items

- GitHub owner, public module path, remote, and license
- Whether to correct or explicitly accept the Go environment warning
- Frozen Python/Go parity fixtures and thresholds for catalog coverage,
  exact-load bytes/metadata, and search ranking
- Search-weight quality and cache cold/warm latency
- Live Codex bootstrap behavior and end-to-end skill application
- Token overhead and total-request token measurements
- Catalog hot reload, Docker, HTTP, release packaging, and platform compatibility

## Next review slice

1. Review the current branch commit against base commit `3d4caa0`.
2. Re-run the commands above and inspect the six redacted doctor diagnostics.
3. Decide module owner/path, license, and Go environment handling.
4. Commit the reviewed branch before creating another worktree.
5. Build frozen parity fixtures before tuning ranking weights or publishing
   performance and token claims.
