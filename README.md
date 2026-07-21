# SkillLoader

**Keep every skill. Load only the one you need.**

SkillLoader is a Go MCP server prototype that keeps a large skill catalog outside an
AI agent's steady-state context. The agent searches the catalog and loads the
smallest matching skill only when a task needs it.

> Status: local prototype. Core, parity, subprocess MCP, synthetic benchmark,
> and one live Codex routing fixture are verified. Large-catalog product benefit,
> task-completion quality, release packaging, and public multi-client
> compatibility are not complete.

## Why

Registering many skills directly with an AI client can make their names and
descriptions part of the always-available context. SkillLoader is designed to
decouple catalog size from that steady-state prompt cost.

```text
AI client
  |  small bootstrap + MCP tool schemas
  v
SkillLoader MCP server
  |-- search compact metadata
  |-- load one selected skill
  |-- validate trusted catalog roots
  `-- cache indexes and parsed documents
```

The complete catalog stays on the server. A normal task should expose only:

1. the small SkillLoader tool definitions;
2. a bounded set of search matches; and
3. the body of the selected skill.

Every load reads and hashes the current file bytes before consulting the document
cache. The cache avoids re-validating unchanged frontmatter; its core latency
effect is measured only on synthetic fixtures. It does not remove the tokens of
a returned skill body.

## Model-visible MCP tools

| Tool | Purpose |
|---|---|
| `search_skills` | Return a bounded, ranked set of skill metadata |
| `load_skill` | Return one resolved skill document by logical name |

Catalog inspection and diagnostics remain direct CLI commands so their schemas
do not consume model context:

```text
skillloader list --json
skillloader doctor --json
```

The implemented request and response shapes are defined in
[docs/MCP_CONTRACT.md](docs/MCP_CONTRACT.md).

## Current local interface

- Required Go toolchain: `1.26.5` or newer
- One Go binary named `skillloader`
- MCP over stdio for local clients
- Two model-visible MCP tools
- Stable JSON output for direct CLI diagnostics

Live Codex CLI `0.144.6` bootstrap is verified on the versioned 10-skill routing
fixture in an isolated temporary Codex environment. OpenCode `1.18.4` has also
completed a live local search/load and warm-cache check; Claude Code remains
unverified. See
[docs/CLIENT_BOOTSTRAP.md](docs/CLIENT_BOOTSTRAP.md) for registration and
isolated verification commands.

`SKILLLOADER_ROOTS` may override the default roots with a comma-separated list
of literal paths. It performs whitespace trimming only; relative paths resolve
against the process working directory, and quoting, tilde expansion, and glob
expansion are not supported. Search tokenization currently
supports English letters, digits, Hangul, and hyphens.

Streamable HTTP, Docker, and additional client integrations are post-MVP work.
They start only after the local token and routing claims are measured.

The MCP specification defines tools as schema-described interfaces whose calls
return structured or unstructured content. SkillLoader uses typed output schemas,
structured content, and a JSON TextContent compatibility copy:
[MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

## Token claim

No positive token-reduction percentage is proven. In the recorded live Codex
10-skill fixture, SkillLoader reduced the offline initial static estimate by
12.94%, but client-reported total input increased 242.84% because search and
load add model turns. This small synthetic result does not establish a
large-catalog break-even point; see [docs/BENCHMARK.md](docs/BENCHMARK.md) and
[docs/PRODUCT_EVIDENCE.md](docs/PRODUCT_EVIDENCE.md).

## Project documents

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and trust boundaries
- [docs/MCP_CONTRACT.md](docs/MCP_CONTRACT.md) — current prototype interface
- [docs/DEPENDENCY_REVIEW.md](docs/DEPENDENCY_REVIEW.md) — transitive module paths and security checks
- [docs/BENCHMARK.md](docs/BENCHMARK.md) — token, routing, and latency evaluation
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution and verification rules

## Non-goals

- Claiming that caching alone reduces model tokens
- Treating arbitrary downloaded skill documents as trusted instructions
- Sending local filesystem paths as portable skill identifiers
- Claiming compatibility with a client before its integration is tested

## License

MIT. See [LICENSE](LICENSE).
