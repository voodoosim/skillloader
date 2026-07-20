// Benchmark conditions:
//
//	System:      linux/amd64, Go 1.26.5, AMD Ryzen (WSL)
//	Catalog:     50 synthetic SKILL.md files under a temporary directory
//	Measurement: Go testing.B (BenchmarkColdBuild, BenchmarkWarmSnapshot)
//	I/O:         disk I/O excluded; cold benchmark resets timer after BuildIndex
//	             warm benchmark pre-saves snapshot and resets timer before load
//	Scope:       core-process timing; does not measure Go binary startup overhead,
//	             MCP transport, Codex client behavior, or a real user catalog
//
// For I/O-including benchmark evidence across search + load + 100-skill catalog,
// see benchmark_evidence_test.go and bench/results/.

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func BenchmarkColdBuild(b *testing.B) {
	b.Setenv("XDG_CACHE_HOME", b.TempDir())

	tmp := b.TempDir()
	for i := 0; i < 50; i++ {
		dir := filepath.Join(tmp, fmt.Sprintf("skill-%d", i))
		os.MkdirAll(dir, 0755)
		content := []byte(fmt.Sprintf("---\nname: bench-cold-%d\ndescription: bench\ntags: [bench]\n---\n# Body\n", i))
		os.WriteFile(filepath.Join(dir, "SKILL.md"), content, 0644)
	}

	roots := []string{tmp}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		BuildIndex(roots)
	}
}

func BenchmarkWarmSnapshot(b *testing.B) {
	b.Setenv("XDG_CACHE_HOME", b.TempDir())

	tmp := b.TempDir()
	for i := 0; i < 50; i++ {
		dir := filepath.Join(tmp, fmt.Sprintf("skill-%d", i))
		os.MkdirAll(dir, 0755)
		content := []byte(fmt.Sprintf("---\nname: bench-warm-%d\ndescription: bench\ntags: [bench]\n---\n# Body\n", i))
		os.WriteFile(filepath.Join(dir, "SKILL.md"), content, 0644)
	}

	roots := []string{tmp}
	entries, errs, _ := BuildIndex(roots)
	saveSnapshot(entries, errs, roots)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		loadSnapshot(roots)
	}
}
