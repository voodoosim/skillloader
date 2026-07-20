package main

import (
	"os"
	"path/filepath"
	"testing"
)

func BenchmarkColdBuild(b *testing.B) {
	tmp := b.TempDir()
	for i := 0; i < 50; i++ {
		dir := filepath.Join(tmp, "skill-"+string(rune('a'+i%26)))
		os.MkdirAll(dir, 0755)
		os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("---\nname: bench-cold\ndescription: bench\ntags: [bench]\n---\n# Body\n"), 0644)
	}

	clearSnapshot()
	roots := []string{tmp}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		BuildIndex(roots)
	}
}

func BenchmarkWarmSnapshot(b *testing.B) {
	tmp := b.TempDir()
	for i := 0; i < 50; i++ {
		dir := filepath.Join(tmp, "skill-"+string(rune('a'+i%26)))
		os.MkdirAll(dir, 0755)
		os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("---\nname: bench-warm\ndescription: bench\ntags: [bench]\n---\n# Body\n"), 0644)
	}

	roots := []string{tmp}
	entries, _, _ := BuildIndex(roots)
	saveSnapshot(entries)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		loadSnapshot()
	}
}
