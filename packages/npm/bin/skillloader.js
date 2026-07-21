#!/usr/bin/env node
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const binary = path.join(__dirname, process.platform === "win32" ? "skillloader.exe" : "skillloader");
const result = spawnSync(binary, process.argv.slice(2), { stdio: "inherit" });
if (result.error) {
  console.error("skillloader binary not found; install it with: go install github.com/voodoosim/skillloader@latest");
  process.exit(1);
}
process.exit(result.status ?? 1);
