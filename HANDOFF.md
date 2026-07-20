# SkillLoader Handoff

Last verified: 2026-07-20 KST

This file records the current branch state. Historical rationale and
remaining gates belong in `plan.md` and `CODEX_PLAN_BASELINE.md`.

## Observed state

| Surface | State | Evidence |
|---|---|---|
| Project root | `/home/vodo/workspace/projects/skillloader` | `git rev-parse --show-toplevel` |
| Git | Branch `fix/security-runtime-dependencies`, review base `89e2538`, remote `origin` configured | `git branch --show-current`, `git log --oneline`, `git remote` |
| Runtime | Project-selected Go `1.26.5` on `linux/amd64`; `go 1.26.5` also implies the same preferred toolchain | `go.mod`, `GODEBUG=toolchaintrace=1 go version` |
| Go environment | `GOTOOLCHAIN=auto` selects the module toolchain under the module cache; project commands no longer use the host's overlapping `GOPATH`/`GOROOT` | `go env GOVERSION GOTOOLCHAIN GOROOT GOPATH` |
| Implementation | Local Go prototype with catalog, YAML frontmatter parsing, search, trusted-root load, cache, two typed MCP tools, and operator CLI | source tree and tests |
| MCP | In-memory integration test verifies exactly `search_skills` and `load_skill`, output schemas, structured results, TextContent compatibility, and redacted errors | `go test -count=1 ./...` |
| CLI | `list`, `doctor`, `help`, `--help`, and `-h`; help exits 0 | unit test and outside-repository smoke |
| Local catalog | 133 valid parsed skills, 5 errors, 133 missing-tag warnings | `go run . doctor --json` |
| Module | `github.com/voodoosim/skillloader`; MCP SDK `v1.6.1`; YAML `v3.0.4` | `go.mod` |
| License | MIT | `LICENSE` |

The five current doctor errors are four invalid frontmatter diagnostics whose
documents lack an opening YAML delimiter plus one duplicate logical-name
diagnostic. `skill_count`,
`error_count`, and `warning_count` are independent diagnostic dimensions.

## Decisions applied in this branch

- Require Go `1.26.5` so builds use the latest stable security-patched toolchain
  selected for this project.
- Use the official Go MCP SDK `v1.6.1`; the prior `v1.2.0` dependency was inside
  four GitHub advisory ranges.
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
go mod tidy                                pass
go mod verify                              pass
gofmt -d *.go                              clean
go test -count=1 ./...                     pass (38 top-level test functions)
go test -race -count=1 ./...               pass
go vet ./...                               pass
go build ./...                             pass
go run .../govulncheck@latest ./...         0 vulnerabilities
go run . doctor --json                     133 skills / 5 errors / 133 warnings
outside-repository help/list/doctor         pass
outside-repository stdio EOF smoke          pass, exit 0
```

The host bootstrap Go outside this module still needs separate environment
cleanup; project commands use the automatically selected Go `1.26.5` toolchain.

## Exact unverified items

- Host-level `GOPATH == GOROOT` cleanup outside the module toolchain
- Independent review of this dependency-only branch before integration
- The inherited duplicate-name auto-resolution in `89e2538`, which conflicts
  with the rejection policy in `AGENTS.md`, `plan.md`, and `docs/MCP_CONTRACT.md`
- Frozen Python/Go parity fixtures and thresholds for catalog coverage,
  exact-load bytes/metadata, and search ranking
- Search-weight quality and cache cold/warm latency
- Live Codex bootstrap behavior and end-to-end skill application
- Token overhead and total-request token measurements
- Catalog hot reload, Docker, HTTP, release packaging, and platform compatibility

## Next review slice

1. Review this branch against base commit `89e2538`.
2. Re-run the commands above and inspect the five redacted doctor diagnostics.
3. Resolve the inherited duplicate-name contract conflict in a separate branch.
4. Build frozen parity fixtures before tuning ranking weights or publishing
   performance and token claims.
