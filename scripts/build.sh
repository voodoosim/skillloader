#!/bin/sh
set -eu

PROJECT="github.com/voodoosim/skillloader"
VERSION="${1:-dev}"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")"
LDFLAGS="-s -w -X main.version=${VERSION} -X main.commit=${COMMIT}"
DIST="./dist"

mkdir -p "${DIST}"

echo "==> Building skillloader ${VERSION} (${COMMIT})"

go build -trimpath -ldflags "${LDFLAGS}" -o "${DIST}/skillloader" .
echo "    ${DIST}/skillloader"

echo
echo "==> Running tests"
go test -count=1 ./...
go vet ./...
echo
echo "==> Verifying binary"
"${DIST}/skillloader" help 2>&1
"${DIST}/skillloader" list 2>&1 | head -3
echo
echo "==> Done. Binary: ${DIST}/skillloader"
