# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SkillLoader is a Go MCP (Model Context Protocol) server that keeps a large
AI-agent skill catalog out of an agent's steady-state context. Instead of
registering every skill's name/description directly with a client, the agent
calls two bounded MCP tools — `search_skills` and `load_skill` — and the
server resolves matches from `SKILL.md` files under trusted catalog roots.

Status: local prototype. Do not overstate token-reduction or compatibility
claims — see the "No unverified claims" rule below.

## Commands

Build the binary (includes tests, vet, and a smoke check):

```bash
./scripts/build.sh [version]
# binary at ./dist/skillloader
```

Run all tests:

```bash
go test -count=1 ./...
```

Run a single test:

```bash
go test -run TestName ./...
```

Race detector (required for cache/concurrency changes):

```bash
go test -race -count=1 ./...
```

Vet, module verification, and vulnerability scan:

```bash
go vet ./...
go mod verify
go run golang.org/x/vuln/cmd/govulncheck@latest ./...
```

Standalone binary smoke test (isolated temp `$XDG_CACHE_HOME`, isolated skill root):

```bash
./scripts/smoke-test.sh
```

Manual local run (starts the stdio MCP server):

```bash
go run .
```

CLI diagnostics (no MCP client needed):

```bash
go run . list --json
go run . doctor --json
```

Live Codex routing/token benchmark (network + Codex CLI required):

```bash
python3 scripts/run_gate6_codex.py
```

For dependency/toolchain changes, also run `go mod why -m <module-path>` and
`go mod graph`, and record results in `docs/DEPENDENCY_REVIEW.md`.

Go toolchain requirement: `1.26.5` or newer (see `go.mod`).

## Architecture

Everything lives in `package main` at the repo root (no internal packages).
Files are split by responsibility, not by layer boundary:

- **`main.go`** — process entrypoint, CLI dispatch (`runCLI`), and MCP server
  wiring (`newServer`). Defines the two model-visible tools (`search_skills`,
  `load_skill`), their input/output structs, and root-list resolution
  (`SKILLLOADER_ROOTS` env var or `DefaultRoots()`).
- **`catalog.go`** — catalog discovery and parsing. `DiscoverSkills` walks
  trusted roots (via `os.OpenRoot`, not raw `filepath.Walk`) for `SKILL.md`
  files; `ParseSkill`/`parseSkillData` extract YAML frontmatter
  (`name`/`description`/`tags`) without pulling in a full YAML→struct
  decode of untrusted content. `readTrustedFile` is the single chokepoint
  that re-validates every file path stays inside a configured root
  (symlink-resolved) before any read — this is the trust boundary; do not
  bypass it when adding new read paths.
- **`loader.go`** — `SkillLoader.Load` resolves a logical skill name to
  exactly one catalog entry (rejects zero or ambiguous >1 matches), re-reads
  and re-validates the file through `readTrustedFile`, and confirms the
  frontmatter `name` still matches the indexed name before returning content.
  All errors are mapped to a small set of stable, redacted `SkillError` codes
  (`SKILL_NOT_FOUND`, `AMBIGUOUS_SKILL`, `UNSAFE_SOURCE`, `INVALID_SKILL`,
  `INVALID_ARGUMENT`) — never leak raw filesystem errors to the model.
- **`search.go`** — `SearchEngine.Search` runs a deterministic 8-layer
  ranking pipeline (tokenize → tag match → name match → description match →
  aggregate → drop description-only fallback if a strong match exists →
  reject ambiguous names → filter unsafe/zero-score entries → truncate to
  `limit`). Ranking weights are prototype constants, not tuned against a
  frozen relevance fixture — treat changes to them as behavior changes
  requiring `parity_test.go`/benchmark re-verification.
- **`cache.go`** — in-memory `Cache`: holds the current catalog index (keyed
  by a content-derived hash) and per-path parsed document bodies, invalidated
  on checksum mismatch. Thread-safe via `sync.RWMutex`; any change here needs
  `-race` coverage.
- **`snapshot.go`** — on-disk cold-start cache at
  `$XDG_CACHE_HOME/skillloader/catalog.gob`, keyed by root paths + a
  directory fingerprint + per-file mtime/size. Falls back to a fresh
  `BuildIndex` on any mismatch or decode failure — never trust a stale
  snapshot into serving content.
- **`doctor.go`** — `Doctor`/`DoctorJSON`/`ListJSON`/`ListText` back the
  `doctor` and `list` CLI subcommands: duplicate-name detection, missing-tag
  warnings, and unreadable/non-directory root checks.

### Trust model

Catalog roots (`~/.codex/skills`, `~/.codex/disabled-skills`,
`~/.agents/skills`, `~/.claude/skills` by default, or
`SKILLLOADER_ROOTS`) are the trust boundary. Every file read — discovery,
parse, and load — goes through path containment checks that resolve
symlinks and reject anything outside its configured root
(`errOutsideTrustedRoots`) or unreadable (`errUnreadableSkill`). Skill
document _content_ itself is still untrusted instruction text once loaded;
SkillLoader's job stops at proving the source path was legitimate, not at
vetting document contents.

### MCP surface

Only two tools are model-visible (`search_skills`, `load_skill`); this is
deliberate (see `CONTRIBUTING.md` — "Keep the two-tool MCP surface small").
Diagnostics (`list`, `doctor`) are direct CLI commands specifically so their
schemas don't add steady-state token cost. Both tools support
result-hash short-circuiting (`known_query_hash`, `known_content_sha256`) so
a client that already has the current value gets `cached: true` with no
payload. The exact request/response shapes are the source of truth in
`docs/MCP_CONTRACT.md` — update it together with `main.go` when the surface
changes.

## Testing conventions

- `testdata/parity/` holds frozen fixture queries/loads
  (`frozen_queries.json`, `frozen_loads.json`) plus a synthetic
  `.codex`/`.claude` home tree; `parity_test.go` and `integration_test.go`
  replay these to catch ranking/output regressions.
- `benchmark_evidence_test.go` / `bench_test.go` back the numbers cited in
  `docs/BENCHMARK.md` — don't change scoring constants or cache behavior
  without re-running these and updating that doc.
- `mcp_test.go` / `stdio_test.go` exercise the actual MCP stdio transport,
  not just internal functions.

## No unverified claims

This project's own `CONTRIBUTING.md` rule applies to any doc or comment you
write here too: every performance, token-reduction, or client-compatibility
statement must link to reproducible local evidence (a test, benchmark
script, or fixture in this repo) or an authoritative external spec — not
inference. Before adding language like "supported", "compatible", or a
percentage improvement, check it against `README.md`'s existing hedged
claims (e.g. "No positive token-reduction percentage is proven") and
`docs/BENCHMARK.md`/`docs/PRODUCT_EVIDENCE.md`.

## Packaging

`packages/npm/` (published as `skillloader-mcp` on npm) and
`packages/python/` are thin launchers that download/invoke the Go binary —
they are not where core logic lives. Release binaries are built via
`.github/workflows/` and installed via `scripts/install.sh` (Unix) or the
`.exe` GitHub release asset (Windows). Pinned-version installs and the
`SKILLLOADER_SOURCE_DIR` local/offline install path are documented in
`INSTALL.md`.
