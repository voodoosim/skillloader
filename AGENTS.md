# SkillLoader Agent Instructions

## Start here

Read `HANDOFF.md`, then `plan.md`, before interpreting project status or making
changes. Verify the Git root, branch, and worktree first.

## Current status

The repository contains a Go prototype for the catalog, search, loader, cache,
two MCP tools, and operator CLI. Do not claim live Codex integration, Python
parity, benchmark results, release packaging, Docker support, token reduction,
or a compatibility matrix until verification evidence exists.

## Product invariants

- Keep the full skill catalog outside the model's steady-state context.
- Return bounded search results and load only explicitly selected skills.
- Treat caching as a latency optimization, not a token-saving mechanism.
- Identify skills by logical name; never accept an arbitrary path from a client.
- Restrict catalog resolution to configured trusted roots.
- Keep the MVP local and stdio-only; defer HTTP and Docker until its evidence
  gates pass.
- Label token savings as measured only when backed by `docs/BENCHMARK.md` data.

## Implementation direction

- Language: Go.
- Binary: `skillloader`.
- Protocol: MCP.
- Model-visible MCP tools: `search_skills`, `load_skill`.
- Operator CLI commands: `list`, `doctor`.
- Output: stable structured results with redacted errors.

Use the official Go MCP SDK unless an evidence-backed decision records a
different choice:
https://github.com/modelcontextprotocol/go-sdk

## Safety

- Never read or store credentials, tokens, `.env` contents, or private keys.
- Reject traversal outside configured roots and ambiguous duplicate names.
- Preserve unrelated user changes.
- Preserve the correctly spelled project root: `/home/vodo/workspace/projects/skillloader`.

## Verification

For Go or documentation changes, run and record:

```bash
gofmt -d *.go
go test -count=1 ./...
go test -race -count=1 ./...
go vet ./...
go build ./...
git diff --check
git status --short
rg -n "90%|implemented|supported|compatible" README.md HANDOFF.md plan.md docs
```

Parity, benchmark, live-client, and outside-repository smoke claims require their
own exact commands and evidence.
