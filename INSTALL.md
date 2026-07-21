# Install SkillLoader

## Requirements

- Go 1.26.5 or newer
- `git` (if installing from source)

## Recommended one-line install

```bash
go install github.com/voodoosim/skillloader@latest
```

Pin a specific published version by replacing `latest`, for example:

```bash
go install github.com/voodoosim/skillloader@v0.1.1
```

This downloads and builds the binary into `$GOPATH/bin/skillloader` (default
`~/go/bin/`).

The command above is the simplest reproducible Go-native install. For a user-local
Unix install that also places the binary in `~/.local/bin`:

On Unix-like systems with Go 1.26.5 or newer:

```bash
curl -fsSL https://raw.githubusercontent.com/voodoosim/skillloader/main/scripts/install.sh | sh
```

The installer defaults to `latest`; pin a version with:

```bash
curl -fsSL https://raw.githubusercontent.com/voodoosim/skillloader/main/scripts/install.sh | SKILLLOADER_VERSION=v0.1.1 sh
```

The script installs to `~/.local/bin/skillloader`, verifies `skillloader help`,
and does not modify client configuration. To register Codex explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/voodoosim/skillloader/main/scripts/install.sh | sh -s -- --configure-codex
```

The installer is Unix-only. Windows users should use the `.exe` asset from the
[latest release](https://github.com/voodoosim/skillloader/releases/latest).

Releases are retained for pinned versions, offline installation, and checksum
review; they are not required for the normal one-line install path.

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

Codex can be registered during installation with `--configure-codex` above.
Other MCP clients use the same local stdio command; copy the JSON below into
the client's MCP configuration.

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
