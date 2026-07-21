# SkillLoader Handoff

Last verified: 2026-07-21 KST

This file records the current branch state. Historical rationale and
remaining gates belong in `plan.md` and `CODEX_PLAN_BASELINE.md`.

## Observed state

| Surface | State | Evidence |
|---|---|---|
| Project root | `/home/vodo/workspace/projects/skillloader` | `git rev-parse --show-toplevel` |
| Git | Branch `main`, base commit `782d2b3` equals `origin/main`; product-evidence changes are uncommitted | `git branch --show-current`, `git rev-parse`, `git status --short` |
| Runtime | Project-selected Go `1.26.5` on `linux/amd64`; `go 1.26.5` also implies the same preferred toolchain | `go.mod`, `GODEBUG=toolchaintrace=1 go version` |
| Go environment | `GOTOOLCHAIN=auto` selects the module toolchain under the module cache; project commands no longer use the host's overlapping `GOPATH`/`GOROOT` | `go env GOVERSION GOTOOLCHAIN GOROOT GOPATH` |
| Implementation | Local Go prototype with catalog, YAML frontmatter parsing, search, duplicate-name rejection, trusted-root load, cache, two typed MCP tools, and operator CLI | source tree and tests |
| MCP | In-memory and subprocess stdio tests verify exactly `search_skills` and `load_skill`; live Codex CLI `0.144.6` executed both tools with complete document results | `go test -count=1 ./...`, `scripts/smoke-test.sh`, Gate 6 redacted JSONL evidence |
| CLI | `list`, `doctor`, `help`, `--help`, and `-h`; help exits 0 | unit test and outside-repository smoke |
| Local catalog | 133 valid parsed skills, 5 errors, 133 missing-tag warnings | `go run . doctor --json` |
| Module | `github.com/voodoosim/skillloader`; MCP SDK `v1.6.1`; YAML `v3.0.4` | `go.mod` |
| License | MIT | `LICENSE` |
| Product evidence | 24/24 isolated live Codex executions completed; after correcting one scoring-only fixture oracle, eager routing-fixture success was 10/12 and SkillLoader was 11/12; SkillLoader raw search top-1 was 8/10 and top-5 recall was 9/10 | `bench/results/2026-07-21-codex-0.144.6-gate6-isolated/summary.json` |
| Token/latency result | On the 10-skill fixture, SkillLoader initial static estimate was 12.94% lower, but total input increased 242.84%, uncached input increased 10.81%, and wall time increased 122.72% | same summary and `docs/PRODUCT_EVIDENCE.md` |

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
- Treat the live Codex 10-skill comparison as negative small-catalog product
  evidence, not as a token-saving claim or a large-catalog break-even result.
- Keep routing-fixture success separate from task-completion success; the
  committed 12 queries do not execute substantive end tasks.

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
live Codex eager/SkillLoader paired runs    pass (24/24 process executions)
live Codex MCP tool errors                  0
Gate 6 artifact integrity                   pass (12 tasks + 12 eager + 12 MCP)
Gate 6 secret-pattern scan                  clean
Gate 6 runner regression tests              pass (37 tests)
safe-environment live paired smoke           pass (2/2 executions)
independent uncommitted review               44 findings addressed; final re-review found no prioritized defects
```

The host bootstrap Go outside this module still needs separate environment
cleanup; project commands use the automatically selected Go `1.26.5` toolchain.

## Exact unverified items

- Host-level `GOPATH == GOROOT` cleanup outside the module toolchain
- Live Claude Code and OpenCode bootstrap behavior
- Task-completion quality after applying a loaded skill
- Repeated-run statistical stability and a real/large-catalog break-even point
- Catalog hot reload, Docker, HTTP, release packaging, and platform compatibility

## Next review slice

1. Fix or explicitly reject the `릴리스 노트 작성해줘` fixture expectation; the
   current Korean query has no match against English-only release metadata.
2. Add repeated large-catalog runs before claiming a token or latency benefit.
3. Run isolated Claude Code and OpenCode bootstraps without changing credentials
   or global configuration.
