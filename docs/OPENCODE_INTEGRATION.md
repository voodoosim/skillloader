# OpenCode Integration

Add this entry to `~/.config/opencode/opencode.json` under the `mcp` key:

```json
{
  "skillloader": {
    "type": "local",
    "command": ["/home/vodo/workspace/projects/skillloader/skillloader"],
    "environment": {
      "SKILLLOADER_ROOTS": "/home/vodo/.codex/skills,/home/vodo/.claude/skills,/home/vodo/.agents/skills,/home/vodo/.codex/disabled-skills"
    },
    "enabled": true
  }
}
```

After editing, restart Opencode. SkillLoader exposes two tools to the model:

- `search_skills` — search the skill catalog by task description
- `load_skill` — load a full skill document by exact name

## Verification

Build the binary and run the smoke tests:

```bash
cd ~/workspace/projects/skillloader
go build -o skillloader .
bash scripts/smoke-test.sh
```

Verify the MCP stdio round trip:

```bash
go test -count=1 -run '^TestStdioMCPProcessRoundTrip$' ./...
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SKILLLOADER_ROOTS` | `~/.codex/skills,~/.codex/disabled-skills,~/.agents/skills,~/.claude/skills` | Comma-separated trusted roots |
| `XDG_CACHE_HOME` | `~/.cache` | Directory for the gob catalog snapshot |

## Safety

- SkillLoader rejects paths outside configured roots.
- Only two tools are visible to the model.
- Error responses redact filesystem paths.
- Ambiguous (duplicate) skill names are rejected at load time.
