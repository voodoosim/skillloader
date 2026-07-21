#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const result = spawnSync("skillloader", process.argv.slice(2), { stdio: "inherit" });
if (result.error) {
  console.error("skillloader binary not found; install it with: go install github.com/voodoosim/skillloader@latest");
  process.exit(1);
}
process.exit(result.status ?? 1);
