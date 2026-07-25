# Client bootstrap

SkillLoader exposes one local MCP stdio server. Claude Code, Codex, and
OpenCode use the same binary and trusted-root environment; only their client
registration syntax differs.

Set these placeholders per machine:

```text
SKILLLOADER_BIN=/absolute/path/to/skillloader
SKILLLOADER_ROOTS=/absolute/path/to/skills
```

Do not put credentials or private skill contents in these examples.

## Claude Code

For a project-scoped configuration, create `.mcp.json` (or use the equivalent
`claude mcp add --scope project` command):

```json
{
  "mcpServers": {
    "skillloader": {
      "command": "/absolute/path/to/skillloader",
      "args": [],
      "env": {
        "SKILLLOADER_ROOTS": "/absolute/path/to/skills"
      }
    }
  }
}
```

Validate without changing user configuration:

```bash
claude -p "Use search_skills to find a relevant skill, then load exactly one." \
  --mcp-config /absolute/path/to/.mcp.json \
  --output-format json
```

The `--mcp-config` option and `.mcp.json` shape are documented by Anthropic:
<https://docs.anthropic.com/en/docs/claude-code/mcp>.

A live round trip (`search_skills` then `load_skill` against a real, non-synthetic
local catalog) was recorded on Claude Code CLI `2.1.212` via `claude mcp add`
project-scoped registration; both calls returned valid, checksum-matching
results. See `bench/results/2026-07-25-claude-code-2.1.212-live-roundtrip/`.

A separate, isolated Gate-6-equivalent eager-vs-SkillLoader comparison (same
12-task, 10-skill fixture used against Codex) was also run on Claude Code CLI
`2.1.212` and is recorded in
`bench/results/2026-07-25-claude-code-2.1.212-gate6-isolated/`; see
`docs/BENCHMARK.md` "Live Claude Code routing evidence" for the results and
isolation method. It shows no positive token or cost saving at this small
catalog size, plus a Claude-Code-specific `ToolSearch` deferred-tool-resolution
overhead with no Codex analogue — see "Common verification" below for what
still remains unestablished.

## Codex

Register the same stdio command with the Codex CLI:

```bash
codex mcp add skillloader --env SKILLLOADER_ROOTS="$SKILLLOADER_ROOTS" \
  -- "$SKILLLOADER_BIN"
codex mcp list
```

Use a temporary Codex config or a disposable environment for validation. Do
not modify a shared config when running CI or an independent review.

## OpenCode

OpenCode accepts a local server entry in its project configuration:

```json
{
  "mcp": {
    "skillloader": {
      "type": "local",
      "command": ["/absolute/path/to/skillloader"],
      "environment": {
        "SKILLLOADER_ROOTS": "/absolute/path/to/skills"
      },
      "enabled": true
    }
  }
}
```

For a CLI-managed entry, inspect the generated configuration with:

```bash
opencode mcp add skillloader --env SKILLLOADER_ROOTS="$SKILLLOADER_ROOTS" \
  -- "$SKILLLOADER_BIN"
opencode mcp list
```

Use an isolated project/configuration for validation; never overwrite an
existing user configuration in a test.

## Common verification

All three clients must expose only `search_skills` and `load_skill`. The
protocol-level checks are client-independent and run locally:

```bash
go test -count=1 -run '^TestStdioMCPProcessRoundTrip$' ./...
bash scripts/smoke-test.sh
```

Live model behavior is not established by these commands. A client-specific
run must record the exact client version, configuration scope, selected skill,
and complete loaded document before claiming live compatibility.

The Codex CLI `0.144.6` and Claude Code CLI `2.1.212` live evidence meeting
those requirements is recorded in
`bench/results/2026-07-21-codex-0.144.6-gate6-isolated/` and
`bench/results/2026-07-25-claude-code-2.1.212-gate6-isolated/`, documented in
`docs/BENCHMARK.md` and `docs/PRODUCT_EVIDENCE.md`. OpenCode `1.18.4` was
also verified in the current environment for local search/load and
warm-cache reuse. This does not establish cross-platform Claude Code or
OpenCode behavior beyond what is recorded, a real-catalog or large-catalog
break-even point for either client, or that the two clients' token/cost
totals are comparable to each other (their usage-accounting fields differ in
shape).
