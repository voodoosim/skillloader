# Architecture

## Goal

Keep catalog growth on the server side while keeping the model-visible
SkillLoader interface small and stable.

```text
                         trusted roots
                              |
                              v
+-----------+ MCP +---------------------------+
| AI client |---->| SkillLoader                |
|           |     |  protocol adapter          |
| bootstrap |     |       |                    |
+-----------+     |  application services      |
                  |      | search | load |      |
                  |       |                    |
                  |  catalog index + cache     |
                  +---------------------------+
                        ^             ^
                        | CLI list    | CLI doctor
```

## Components

### Protocol adapter

Accepts typed MCP calls, validates inputs, invokes application services, and
returns bounded structured results. The adapter must not contain ranking or
filesystem policy.

### Catalog

Builds compact metadata entries from configured trusted roots. A catalog entry
is expected to contain a logical name, description, tags, source identifier,
content checksum, and validation state. Raw local paths remain diagnostic data
and are not portable identifiers.

### Search

Ranks compact metadata without reading every full document per request. Equal
inputs and equal catalog state must produce equal ordering. The result limit is
bounded by server policy.

### Loader

Resolves exactly one logical name, verifies that the resolved document remains
inside a trusted root, validates its format, and returns its complete content.
Ambiguous names fail instead of choosing an arbitrary document.

### Operator CLI

Provides `list` and `doctor` without exposing their schemas to the model.
`doctor` reports root readability, invalid documents, duplicates, cache state,
and catalog counts. Diagnostics must not expose secrets or uncontrolled file
contents.

### Cache

The prototype uses an in-process metadata index and document cache. Each load
securely reads and hashes the current file bytes before using a cached document,
so changed and removed files do not return stale content.
Exact size and eviction policy remain benchmark decisions.

The cache avoids repeated frontmatter validation, but it does not avoid the file
read or SHA-256 calculation. Its latency effect is unmeasured. A cached document
still costs model tokens when its content is returned to the model.

## Request sequence

1. A small client bootstrap tells the model to use SkillLoader for a task that
   needs specialist guidance.
2. The model calls `search_skills` with the complete task description.
3. The server returns at most the requested bounded number of metadata matches.
4. The model chooses the narrowest suitable match.
5. The model calls `load_skill` with its logical name.
6. The server returns that validated document.
7. The client presents the tool result to the model as task context.

MCP tools are model-controlled, while resources are application-controlled and
prompts are user-controlled. The first implementation uses tools because the
model must search and select at task time:
https://modelcontextprotocol.io/docs/learn/server-concepts

## Context-cost model

Let:

- `N` be the number of catalog skills;
- `K` be the bounded search-result count;
- `B` be the selected skill body size; and
- `T` be the fixed SkillLoader tool and bootstrap overhead.

An eager catalog has catalog overhead that grows with `N`. The intended lazy
path exposes approximately `T + K metadata entries + B` for a routed task. This
is a design model, not a measured token claim.

## Trust boundaries

- Catalog roots are configured by the operator, not supplied per tool call.
- Tool inputs never accept an arbitrary filesystem path.
- Resolved and symlinked paths must remain under an allowed root.
- Duplicate logical names are errors until an explicit source policy resolves
  them.
- Skill content is instruction-bearing data and must come from trusted sources.
- HTTP transport requires a separate authentication and network-exposure design
  and is excluded from the MVP.
- Stdio is the MVP transport because it keeps the initial trust boundary local.

## Portability boundary

The MCP protocol standardizes tool discovery, calls, and results. It does not
guarantee that every client gives returned text identical instruction priority.
Each supported client therefore needs a tested, minimal bootstrap integration.
Tool results are defined by the official MCP specification:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools
