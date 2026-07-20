# SkillLoader

**Keep every skill. Load only the one you need.**

SkillLoader is a planned MCP server that keeps a large skill catalog outside an
AI agent's steady-state context. The agent searches the catalog and loads the
smallest matching skill only when a task needs it.

> Status: documentation scaffold. No runnable server exists yet.

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

Caching improves catalog lookup and file-loading latency. It does not remove the
tokens of a skill body after that body is returned to the model.

## Planned model-visible MCP tools

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

The proposed request and response shapes are defined in
[docs/MCP_CONTRACT.md](docs/MCP_CONTRACT.md).

## Planned delivery

- One Go binary named `skillloader`
- MCP over stdio for local clients
- Two model-visible MCP tools
- One verified Codex bootstrap integration for the MVP
- Stable JSON output for direct CLI diagnostics

Streamable HTTP, Docker, and additional client integrations are post-MVP work.
They start only after the local token and routing claims are measured.

The MCP specification defines tools as schema-described interfaces whose calls
return structured or unstructured content. SkillLoader will use that standard
boundary rather than inventing a client-specific transport:
[MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

## Token claim

The target is a **90% reduction in skill-catalog overhead**, not a guaranteed
90% reduction in every request's total tokens. No percentage is considered
proven until the reproducible benchmark in
[docs/BENCHMARK.md](docs/BENCHMARK.md) produces it.

## Project documents

- [HANDOFF.md](HANDOFF.md) — current project state
- [plan.md](plan.md) — implementation sequence and open decisions
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components and trust boundaries
- [docs/MCP_CONTRACT.md](docs/MCP_CONTRACT.md) — proposed public interface
- [docs/BENCHMARK.md](docs/BENCHMARK.md) — token, routing, and latency evaluation
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution and verification rules

## Non-goals

- Claiming that caching alone reduces model tokens
- Treating arbitrary downloaded skill documents as trusted instructions
- Sending local filesystem paths as portable skill identifiers
- Claiming compatibility with a client before its integration is tested

## License

Not selected yet. A license must be chosen before public release.
