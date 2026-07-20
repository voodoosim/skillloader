# SkillLoader Handoff

Last verified: 2026-07-20 KST

This file is the current-state source of truth. Historical work and upcoming
steps belong in `plan.md`.

## Observed state

| Surface | State | Evidence |
|---|---|---|
| Project root | `/home/vodo/workspace/projects/skillloader` | `git rev-parse --show-toplevel` |
| Git | Local repository on `main`; no remote configured | `git branch --show-current`, `git remote -v` |
| Runtime | Go `1.25.0` is installed at `/home/vodo/go/bin/go` | `go version`, `command -v go` |
| Go environment | Effective `GOPATH` and `GOROOT` are both `/home/vodo/go`; Go emits an installation warning | `go env GOPATH GOROOT` |
| Implementation | No Go module or runnable server yet | repository file inventory |
| License | Not selected | repository file inventory |
| Legacy draft | Initial misspelled directory retired after its scope was incorporated here | filesystem check |
| Existing loader | Local Python loader reports 82 skills and 0 errors | `skill_loader.py doctor` |

## Decisions recorded

- Build the core as a Go binary named `skillloader`.
- Keep the catalog server-side and load a skill only after bounded search.
- Expose only `search_skills` and `load_skill` to the model over MCP.
- Keep `list` and `doctor` as direct operator CLI commands.
- Keep the MVP local and stdio-only.
- Defer Streamable HTTP, Docker, and a second client until the MVP evidence gates
  pass.
- Use in-memory indexes and parsed-document caching for latency.
- Measure token reduction separately from cache performance.
- Use `skillloader` consistently for the project, binary, and MCP server name.
- Require a thin client bootstrap that tells the model when to search and how to
  apply a loaded skill.

## Files created in the scaffold

- `README.md`
- `AGENTS.md`
- `HANDOFF.md`
- `plan.md`
- `CONTRIBUTING.md`
- `.gitignore`
- `docs/ARCHITECTURE.md`
- `docs/MCP_CONTRACT.md`
- `docs/BENCHMARK.md`

## Exact unverified items

- Go module path and GitHub repository owner
- Open-source license
- Correct Go environment layout; current `GOPATH`/`GOROOT` equality emits a warning
- Official Go MCP SDK version to pin
- CLI flag names
- Codex bootstrap behavior
- Routing quality, cache latency, and token-reduction measurements

## Next implementation slice

1. Decide the module path and license.
2. Correct or explicitly accept the observed Go environment warning.
3. Create the smallest vertical slice: catalog, search, load, and stdio MCP.
4. Verify all 82 current skills load and the frozen search cases match Python.
5. Run the Codex integration and token benchmark gates in `plan.md`.
