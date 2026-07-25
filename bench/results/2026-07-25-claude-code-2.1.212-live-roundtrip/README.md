# Claude Code live round-trip evidence

- Client: Claude Code CLI `2.1.212`
- Registration: `claude mcp add skillloader -- /home/vodo/workspace/projects/skillloader/dist/skillloader`
  (project-scoped stdio server, no `SKILLLOADER_ROOTS` override — default roots:
  `~/.codex/skills`, `~/.codex/disabled-skills`, `~/.agents/skills`, `~/.claude/skills`)
- Catalog: the operator's real local skill directories (not a synthetic fixture)
- Date: 2026-07-25

## What this evidence shows

This is a light-weight confirmation that the MCP stdio contract works end-to-end
against a live Claude Code client and a real (non-synthetic) skill catalog. It is
**not** an eager-vs-SkillLoader routing/token comparison in the shape of
`docs/PRODUCT_EVIDENCE.md`'s Codex Gate 6 fixture. No token-reduction or
routing-accuracy claim is made from this evidence.

## Round trip performed

1. `search_skills` called with query
   `"orchestrate multiple subagents in parallel"`.
   Returned 5 ranked matches from the real catalog (`parallel-chain-runner`,
   `agent-chain-orchestrator`, `implementation-planning`, `define-goal`,
   `diagnostic-insight`) with `catalog_revision`
   `sha256:2dc720981d13088a6d8ac2a3352e584d66466ee3bcbb4503f2729029619718eb`.
2. `load_skill` called with `name: "diagnostic-insight"` (a top-5 match from
   step 1, source `claude`).
   Returned the complete skill document, `content_sha256`
   `526b3038ed8bfe7cedcccfe2d1757b4808c847330941d11707c1b318e8156e25`, and the
   loader's frontmatter-name-match check passed (`name` in the returned
   metadata equals the requested logical name).

Both calls are recorded verbatim in `roundtrip.jsonl` in this directory
(raw tool call arguments and raw JSON responses, unmodified).

## Known gap after this evidence

This confirms the stdio MCP contract and trust-boundary path validation work
live under Claude Code. It does **not** establish:

- Claude Code token/routing behavior at catalog scale (the Codex Gate 6 shape
  of evidence)
- Whether Claude Code's own skill-name-based auto-invocation interacts with
  SkillLoader-sourced content differently from natively registered skills
- Any performance or token-reduction claim for the Claude Code client

A Gate-6-equivalent live comparison for Claude Code (eager catalog vs.
SkillLoader-only, client-reported token usage, routing accuracy) remains
unbuilt. See `docs/PRODUCT_EVIDENCE.md`.
