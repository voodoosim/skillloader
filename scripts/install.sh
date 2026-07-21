#!/bin/sh
set -eu

# Install the current published Go module into a user-local bin directory.
# Optional Codex registration is opt-in because it edits user configuration.
INSTALL_DIR=${SKILLLOADER_INSTALL_DIR:-"${HOME}/.local/bin"}
ROOTS=${SKILLLOADER_ROOTS:-"${HOME}/.codex/skills,${HOME}/.codex/disabled-skills,${HOME}/.agents/skills,${HOME}/.claude/skills"}
MODULE=${SKILLLOADER_MODULE:-github.com/voodoosim/skillloader}
VERSION=${SKILLLOADER_VERSION:-latest}
SOURCE_DIR=${SKILLLOADER_SOURCE_DIR:-}

usage() {
    cat <<'EOF'
Usage: install.sh [--configure-codex]

Installs skillloader into ~/.local/bin (override with SKILLLOADER_INSTALL_DIR).
Set SKILLLOADER_ROOTS to configure trusted catalog roots.
--configure-codex additionally runs `codex mcp add` and changes Codex config.
EOF
}

configure_codex=false
for argument in "$@"; do
    case "$argument" in
        --configure-codex) configure_codex=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $argument" >&2; usage >&2; exit 2 ;;
    esac
done

command -v go >/dev/null 2>&1 || {
    echo "go 1.26.5 or newer is required" >&2
    exit 1
}
mkdir -p "$INSTALL_DIR"
if [ -n "$SOURCE_DIR" ]; then
    go build -trimpath -o "$INSTALL_DIR/skillloader" "$SOURCE_DIR"
else
    GOBIN="$INSTALL_DIR" go install "${MODULE}@${VERSION}"
fi
binary="$INSTALL_DIR/skillloader"
test -x "$binary"
"$binary" help >/dev/null
echo "installed: $binary"
echo "trusted roots: $ROOTS"

if "$configure_codex"; then
    command -v codex >/dev/null 2>&1 || {
        echo "codex is required for --configure-codex" >&2
        exit 1
    }
    codex mcp add skillloader --env "SKILLLOADER_ROOTS=$ROOTS" -- "$binary"
    echo "registered Codex MCP server: skillloader"
fi
