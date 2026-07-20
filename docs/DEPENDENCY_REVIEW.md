# Dependency Review

Last verified: 2026-07-20 KST

This record covers the transitive modules added when the official Go MCP SDK
was upgraded from `v1.2.0` to `v1.6.1`. It records observed dependency paths
and known-vulnerability checks; it is not a claim that third-party code is free
of all defects.

## Observed dependency paths

The following commands were run from the repository root:

```bash
go mod why -m github.com/segmentio/encoding
go mod why -m github.com/segmentio/asm
go mod graph | rg 'segmentio/(asm|encoding)|modelcontextprotocol/go-sdk'
```

They produced these package-level paths:

```text
github.com/voodoosim/skillloader
github.com/modelcontextprotocol/go-sdk/mcp
github.com/modelcontextprotocol/go-sdk/internal/json
github.com/segmentio/encoding/json

github.com/voodoosim/skillloader
github.com/modelcontextprotocol/go-sdk/mcp
github.com/modelcontextprotocol/go-sdk/internal/json
github.com/segmentio/encoding/json
github.com/segmentio/asm/base64
```

The MCP SDK's internal JSON decoder directly imports
`github.com/segmentio/encoding/json`. That module directly requires
`github.com/segmentio/asm`, and its JSON package imports the assembly-backed
base64 package. The selected versions are:

```text
github.com/modelcontextprotocol/go-sdk v1.6.1
github.com/segmentio/encoding v0.5.4
github.com/segmentio/asm v1.1.3
```

These are required build dependencies, not unused `go.sum` entries.

## Integrity and known-vulnerability checks

The following checks passed:

```text
go mod verify
  all modules verified

go env GOSUMDB GONOSUMDB GOINSECURE GOPRIVATE
  GOSUMDB=sum.golang.org
  GONOSUMDB, GOINSECURE, and GOPRIVATE are empty

go run golang.org/x/vuln/cmd/govulncheck@latest -show verbose ./...
  scanned 9 modules and the go1.26.5 standard library
  no vulnerabilities found
```

The repository contains no `replace` directive and no configuration that
disables public module checksum verification. `go.sum` contains the selected
module and module-file hashes.

Go documents `go mod why` as the shortest import path from the main module to a
package in the target module, and `go mod verify` as checking downloaded module
content against recorded hashes:

- https://go.dev/ref/mod#go-mod-why
- https://go.dev/ref/mod#go-mod-verify
- https://go.dev/security/vuln/

## Residual risk

`github.com/segmentio/encoding/json` uses `unsafe`, and its selected
`github.com/segmentio/asm/base64` dependency includes architecture-specific Go
assembly. Those properties expand the third-party audit surface even though the
current source scan reports no known vulnerability. Removing them while keeping
MCP SDK `v1.6.1` would require an upstream SDK dependency change or replacing the
SDK, so the current control is version pinning, checksum verification,
`govulncheck`, race tests, and MCP integration tests.

Re-run this review whenever the MCP SDK or either Segment module changes.
