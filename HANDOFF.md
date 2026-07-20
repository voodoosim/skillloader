# SkillLoader Handoff

Last verified: 2026-07-20 KST

This file records the current branch state. Historical rationale and
remaining gates belong in `plan.md` and `CODEX_PLAN_BASELINE.md`.

## Observed state

| Surface | State | Evidence |
|---|---|---|
| Project root | `/home/vodo/workspace/projects/skillloader` | `git rev-parse --show-toplevel` |
| Git | Branch `main`, latest commit `0262c79` (cross-verification report), remote `origin` configured | `git branch --show-current`, `git log --oneline`, `git remote` |
| Runtime | Project-selected Go `1.26.5` on `linux/amd64`; `go 1.26.5` also implies the same preferred toolchain | `go.mod`, `GODEBUG=toolchaintrace=1 go version` |
| Go environment | `GOTOOLCHAIN=auto` selects the module toolchain under the module cache; project commands no longer use the host's overlapping `GOPATH`/`GOROOT` | `go env GOVERSION GOTOOLCHAIN GOROOT GOPATH` |
| Implementation | Local Go prototype with catalog, YAML frontmatter parsing, search, duplicate-name rejection, trusted-root load, cache, two typed MCP tools, and operator CLI | source tree and tests |
| MCP | In-memory and subprocess stdio tests verify exactly `search_skills` and `load_skill`, output schemas, structured results, TextContent compatibility, and redacted errors | `go test -count=1 ./...`, `scripts/smoke-test.sh` |
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
- Keep the documented duplicate-name rejection policy: ambiguous names are
  excluded from search results and `load_skill` returns `AMBIGUOUS_SKILL`.
- Accept `segmentio/encoding v0.5.4` and `segmentio/asm v1.1.3` as MCP SDK
  transitive build dependencies; their import paths and residual audit surface
  are recorded in `docs/DEPENDENCY_REVIEW.md`.
- Treat the product as a local skill catalog loader/server, not an operating system.
- Treat missing tags as valid with a doctor warning.
- Parse YAML list tags and multiline descriptions; reject documents without YAML
  frontmatter in the MVP.
- Keep search weights deterministic but provisional until fixture-based tuning.
- Return no results for zero-score queries.
- Read and hash current file bytes on every load; use the document cache only
  after checksum verification. Synthetic core timing is recorded; real-catalog
  and client latency remain unmeasured.
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
go test -count=1 ./...                     pass (77 tests)
go test -race -count=1 ./...               pass
go vet ./...                               pass
go build ./...                             pass
go run .../govulncheck@latest ./...         0 vulnerabilities
go mod why -m github.com/segmentio/encoding dependency path recorded
go mod why -m github.com/segmentio/asm      dependency path recorded
go run . doctor --json                     133 skills / 5 errors / 133 warnings
outside-repository help/list/doctor         pass
outside-repository stdio EOF smoke          pass, exit 0
```

The host bootstrap Go outside this module still needs separate environment
cleanup; project commands use the automatically selected Go `1.26.5` toolchain.

## Exact unverified items

- Host-level `GOPATH == GOROOT` cleanup outside the module toolchain
- Live Claude/Codex/OpenCode bootstrap behavior and end-to-end skill application
- Token overhead and total-request token measurements
- Real-catalog benchmark evidence beyond the committed synthetic fixture
- Catalog hot reload, Docker, HTTP, release packaging, and platform compatibility

## Next review slice

1. Run temporary Claude, Codex, and OpenCode MCP bootstraps without changing user credentials
   or global configuration.
2. Verify the live client performs search, one selected load, and full document
   application.
3. Measure token overhead separately from catalog and core-process latency.
