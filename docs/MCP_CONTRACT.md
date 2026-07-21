# MCP Contract

This document defines the current local prototype interface. In-memory protocol
tests cover tool discovery, typed output schemas, structured success results,
redacted structured errors, and the TextContent compatibility copy. Live Codex
CLI `0.144.6` compatibility is verified for the versioned 10-skill routing
fixture in an isolated temporary Codex environment; Claude Code and OpenCode
remain unverified.

## Design rules

- Keep the tool count and descriptions small.
- Use logical names instead of caller-provided paths.
- Bound every collection response.
- Return stable structured data and short human-readable text.
- Return explicit errors for ambiguity, invalid documents, and unsafe paths.
- Never include credentials or unrelated file contents in diagnostics.

The MCP specification permits structured output and recommends returning its
serialized form as text for compatibility. The implementation follows
that behavior:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

## `search_skills`

Search compact catalog metadata.

Input:

```json
{
  "query": "review this Go MCP server for path traversal",
  "limit": 5
}
```

Result:

```json
{
  "matches": [
    {
      "name": "secure-code-review",
      "description": "Review code for concrete security defects.",
      "tags": ["security", "review"],
      "source": "local",
      "score": 84
    }
  ],
  "query": "review this Go MCP server for path traversal",
  "limit": 5,
  "catalog_revision": "sha256:..."
}
```

The response also includes `query_hash` and `cached`. A client may send the
previous `query_hash` as `known_query_hash` on a repeated request with the same
catalog revision. The server then returns `cached: true` and omits `matches`.
The client must reuse the prior result in its session context.

Rules:

- `query` is required and non-empty.
- Valid limits are 1 through 10. Missing or out-of-range values use 5.
- Scores are meaningful only within one catalog revision and ranking version.
- Results contain metadata, not full skill bodies.

## `load_skill`

Resolve and return one validated skill document.

Input:

```json
{
  "name": "secure-code-review"
}
```

Result:

```json
{
  "skill": {
    "name": "secure-code-review",
    "content": "---\nname: secure-code-review\n---\n...",
    "source": "local",
    "content_sha256": "..."
  },
  "catalog_revision": "sha256:..."
}
```

The response includes `content_sha256` and `cached`. A client may send the
previous hash as `known_content_sha256` on a repeated load. The server then
returns `cached: true` and omits the document body. This is a warm-session
token optimization; the first load still returns the complete document.

Rules:

- `name` must be an exact logical name returned by the catalog.
- The input never accepts a path.
- Missing, ambiguous, invalid, or unsafe resolutions fail explicitly.
- Content is returned in full so the client can apply the complete workflow.

## Non-MCP operator CLI

Catalog inspection and diagnostics are intentionally excluded from the
model-visible MCP surface. They are direct CLI commands:

```text
skillloader list --json
skillloader doctor --json
```

`list --json` returns catalog metadata without loading skill bodies.
`doctor --json` returns redacted root, document, duplicate, catalog,
and cache diagnostics. Their stable JSON shapes are a CLI contract and do not
add tool schemas to model context.

`SKILLLOADER_ROOTS` accepts comma-separated literal paths with surrounding
whitespace trimmed. Relative paths resolve against the process working directory.
Quote handling, tilde expansion, and glob expansion are not part of the current
contract.

## Error envelope

Application-level failures are machine-readable tool results with `isError` set:

```json
{
  "catalog_revision": "sha256:...",
  "error": {
    "code": "AMBIGUOUS_SKILL",
    "message": "The logical skill name resolves to multiple trusted sources.",
    "retryable": false
  }
}
```

`catalog_revision` identifies the startup catalog/search snapshot. A loaded
document's `content_sha256` identifies the exact bytes returned. Runtime catalog
hot reload is not implemented; restart the server to refresh search metadata and
the catalog revision.

Initial error codes:

- `INVALID_ARGUMENT`
- `SKILL_NOT_FOUND`
- `AMBIGUOUS_SKILL`
- `INVALID_SKILL`
- `UNSAFE_SOURCE`
- `INTERNAL_ERROR`

## Client bootstrap contract

A client integration should communicate this behavior in its native instruction
surface:

1. Search with the user's complete task when specialist guidance may help.
2. Choose the narrowest match rather than loading broad alternatives.
3. Load one skill; load another only when a required safety gate is separate.
4. Apply the complete returned document for the current task.
5. Route again on the next task instead of carrying the prior skill by inertia.

The exact wording and instruction priority must be tested per client.
