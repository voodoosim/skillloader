#!/usr/bin/env node
const fs = require("node:fs");
const path = require("node:path");
const https = require("node:https");
const platform = process.platform === "win32" ? "windows" : process.platform;
const arch = process.arch === "x64" ? "amd64" : process.arch === "arm64" ? "arm64" : null;
if (!arch || !["linux", "darwin", "windows"].includes(platform)) process.exit(0);
const ext = platform === "windows" ? ".exe" : "";
const asset = `skillloader-v0.1.1-${platform}-${arch}${ext}`;
const target = path.join(__dirname, `skillloader${ext}`);
https.get(`https://github.com/voodoosim/skillloader/releases/download/v0.1.1/${asset}`, res => {
  if (res.statusCode !== 200) { console.error(`download failed: ${res.statusCode}`); process.exit(1); }
  const out = fs.createWriteStream(target); res.pipe(out);
  out.on("finish", () => { out.close(); if (platform !== "windows") fs.chmodSync(target, 0o755); });
}).on("error", err => { console.error(err.message); process.exit(1); });
