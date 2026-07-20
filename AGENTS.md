# SkillLoader Agent Instructions

## Start here

Read `HANDOFF.md`, then `plan.md`, before interpreting project status or making
changes. Verify the Git root, branch, and worktree first.

## Current status

The repository is documentation-only. Do not claim that the server, CLI,
cache, client adapters, Docker image, token reduction, or compatibility matrix
is implemented until code and verification evidence exist.

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

While the repository is documentation-only, run:

```bash
git diff --check
git status --short
rg -n "90%|implemented|supported|compatible" README.md HANDOFF.md plan.md docs
```

After Go code exists, document and run exact format, build, test, race, parity,
benchmark, and smoke-test commands before reporting the implementation as
working.
