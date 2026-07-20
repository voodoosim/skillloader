# Contributing

SkillLoader is currently a local Go prototype. Contributions should keep claims
aligned with verified implementation evidence.

## Before changing the project

1. Read `HANDOFF.md`, `plan.md`, and the relevant document under `docs/`.
2. Run `git status --short` and preserve unrelated changes.
3. State whether the change affects protocol, trust boundaries, token metrics,
   or client compatibility.

## Documentation changes

Run:

```bash
git diff --check
rg -n "90%|implemented|supported|compatible" README.md HANDOFF.md plan.md docs
```

Every performance or compatibility statement must link to reproducible local
evidence or an authoritative external specification.

## Go changes

Every code change should include exact commands for:

- formatting;
- build;
- unit and integration tests;
- race detection where concurrent cache behavior is involved; and
- a built-binary smoke test from outside the repository.

Do not document a command as working until it has been executed successfully in
the current tree.

## Protocol changes

Keep the two-tool MCP surface small. Operator-only capabilities belong in the
CLI. A new MCP tool requires a concrete model workflow that cannot be represented
safely by the existing tools. Update
`docs/MCP_CONTRACT.md`, tests, help output, and compatibility notes together.

## Security

- Never commit credentials, tokens, private skill contents, or copied user data.
- Use sanitized fixtures.
- Treat catalog roots and skill documents as trust-boundary inputs.
- Do not weaken path containment or duplicate-name failures for convenience.
