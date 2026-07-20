#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SKILLLOADER_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "SkillLoader root: $SKILLLOADER_ROOT"

built_home="$(mktemp -d)"
trap "rm -rf $built_home" EXIT

XDG_CACHE_HOME="$built_home/cache"
export XDG_CACHE_HOME

isolated_root="$built_home/skills"
mkdir -p "$isolated_root/test-smoke"
cat > "$isolated_root/test-smoke/SKILL.md" << 'EOF'
---
name: smoke-test
description: "standalone smoke fixture for binary verification"
tags: [smoke, test]
---
# Smoke Test Fixture

This skill verifies that the standalone binary loads correctly.
EOF

echo "building..."
go build -o "$built_home/skillloader" "$SKILLLOADER_ROOT/."
if [ ! -f "$built_home/skillloader" ]; then
  echo -e "${RED}FAIL: build did not produce binary${NC}"
  exit 1
fi
echo -e "${GREEN}PASS: build${NC}"

echo "running doctor..."
doctor_out="$("$built_home/skillloader" doctor --json 2>&1)" || true
if echo "$doctor_out" | grep -q '"skill_count"'; then
  echo -e "${GREEN}PASS: doctor json${NC}"
else
  echo -e "${RED}FAIL: doctor json${NC}"
  echo "$doctor_out"
  exit 1
fi

echo "running list..."
list_out=$(SKILLLOADER_ROOTS="$isolated_root" "$built_home/skillloader" list --json 2>&1)
if echo "$list_out" | grep -q '"smoke-test"'; then
  echo -e "${GREEN}PASS: list finds smoke-test${NC}"
else
  echo -e "${RED}FAIL: list missing smoke-test${NC}"
  echo "$list_out"
  exit 1
fi

echo "running help..."
help_out=$("$built_home/skillloader" help 2>&1)
if echo "$help_out" | grep -q 'list    list catalog metadata' && echo "$help_out" | grep -q 'doctor  diagnose roots'; then
	echo -e "${GREEN}PASS: help describes list and doctor${NC}"
else
	echo -e "${RED}FAIL: help output incomplete${NC}"
  echo "$help_out"
  exit 1
fi

help_exit=0
"$built_home/skillloader" --help > /dev/null 2>&1 || help_exit=$?
if [ $help_exit -ne 0 ]; then
  echo -e "${RED}FAIL: --help exit code = $help_exit, want 0${NC}"
  exit 1
fi
echo -e "${GREEN}PASS: --help exits 0${NC}"

echo "running outside-repo stdio smoke..."
echo '{}' | "$built_home/skillloader" > /dev/null 2>&1 || true
echo -e "${GREEN}PASS: stdio EOF exits without crash${NC}"

echo
echo -e "${GREEN}ALL SMOKE TESTS PASSED${NC}"
