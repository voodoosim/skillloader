# Install SkillLoader

## Requirements

- Go 1.26.5 or newer
- `git` (if installing from source)

## From source (go install)

```bash
go install github.com/voodoosim/skillloader@latest
```

This downloads and builds the binary into `$GOPATH/bin/skillloader` (default
`~/go/bin/`).

## One-line user-local install

On Unix-like systems with Go 1.26.5 or newer:

```bash
curl -fsSL https://raw.githubusercontent.com/voodoosim/skillloader/main/scripts/install.sh | sh
```

The script installs to `~/.local/bin/skillloader`, verifies `skillloader help`,
and does not modify client configuration. To register Codex explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/voodoosim/skillloader/main/scripts/install.sh | sh -s -- --configure-codex
```

This URL becomes usable only after the repository and module are publicly
readable and `scripts/install.sh` is committed to `main`. The installer is
Unix-only; Windows and release binaries remain separate packaging work.

For a local checkout, install without network access:

```bash
SKILLLOADER_SOURCE_DIR="$PWD" scripts/install.sh
```

## From source (manual clone)

```bash
git clone https://github.com/voodoosim/skillloader.git
cd skillloader
./scripts/build.sh
# binary at ./dist/skillloader
```

## Verify

```bash
skillloader help
skillloader doctor --json
```

Expected: `skills` > 0, `error_count` < 10 (legacy documents without YAML
frontmatter are rejected by design).

## Configure for OpenCode / Codex

Add to `~/.config/opencode/opencode.json` (or equivalent):

```json
{
  "mcpServers": {
    "skillloader": {
      "command": "/absolute/path/to/skillloader",
      "environment": {
        "SKILLLOADER_ROOTS": "/home/user/.codex/skills,/home/user/.agents/skills,/home/user/.claude/skills"
      }
    }
  }
}
```

The `SKILLLOADER_ROOTS` variable sets the comma-separated trusted catalog roots.
If omitted, the default roots are `~/.codex/skills`, `~/.codex/disabled-skills`,
`~/.agents/skills`, `~/.claude/skills`.

Restart OpenCode / Codex after configuration. The tools `search_skills` and
`load_skill` will appear in the MCP tool list.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SKILLLOADER_ROOTS` | `~/.codex/skills,...` | Comma-separated trusted catalog roots |
| `XDG_CACHE_HOME` | `~/.cache` | Snapshot storage directory |

Snapshot files are written to `$XDG_CACHE_HOME/skillloader/catalog.gob` for
cold-start acceleration.

## Uninstall

```bash
rm -f "$(which skillloader)"
rm -rf ~/.cache/skillloader
```
