# Proposed MCP Contract

This document defines the first public interface. It is a proposal until the Go
server and protocol tests exist.

## Design rules

- Keep the tool count and descriptions small.
- Use logical names instead of caller-provided paths.
- Bound every collection response.
- Return stable structured data and short human-readable text.
- Return explicit errors for ambiguity, invalid documents, and unsafe paths.
- Never include credentials or unrelated file contents in diagnostics.

The MCP specification permits structured output and recommends returning its
serialized form as text for compatibility. The implementation should follow
that behavior:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

## `search_skills`

Search compact catalog metadata.

Proposed input:

```json
{
  "query": "review this Go MCP server for path traversal",
  "limit": 5
}
```

Proposed result:

```json
{
  "matches": [
    {
      "name": "secure-code-review",
      "description": "Review code for concrete security defects.",
      "tags": ["security", "review"],
      "source": "local",
      "score": 84,
      "reasons": ["tag:security", "term:review"]
    }
  ],
  "query": "review this Go MCP server for path traversal",
  "limit": 5,
  "catalog_revision": "sha256:..."
}
```

Rules:

- `query` is required and non-empty.
- The server applies a configured maximum even if a larger limit is requested.
- Scores are meaningful only within one catalog revision and ranking version.
- Results contain metadata, not full skill bodies.

## `load_skill`

Resolve and return one validated skill document.

Proposed input:

```json
{
  "name": "secure-code-review"
}
```

Proposed result:

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

Rules:

- `name` must be an exact logical name returned by the catalog.
- The input never accepts a path.
- Missing, ambiguous, invalid, or unsafe resolutions fail explicitly.
- Content is returned in full so the client can apply the complete workflow.

## Non-MCP operator CLI

Catalog inspection and diagnostics are intentionally excluded from the
model-visible MCP surface. They are proposed as direct CLI commands:

```text
skillloader list --json
skillloader doctor --json
```

`list --json` pages through catalog metadata without loading skill bodies.
`doctor --json` returns bounded, redacted root, document, duplicate, catalog,
and cache diagnostics. Their stable JSON shapes are a CLI contract and do not
add tool schemas to model context.

## Error envelope

Application-level failures should remain machine-readable tool results:

```json
{
  "error": {
    "code": "AMBIGUOUS_SKILL",
    "message": "The logical skill name resolves to multiple trusted sources.",
    "retryable": false
  }
}
```

Initial error codes:

- `INVALID_ARGUMENT`
- `SKILL_NOT_FOUND`
- `AMBIGUOUS_SKILL`
- `INVALID_SKILL`
- `UNSAFE_SOURCE`
- `CATALOG_UNAVAILABLE`
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
