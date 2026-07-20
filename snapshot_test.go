package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func makeTestEntries(t *testing.T, dir string, count int) []SkillEntry {
	t.Helper()
	entries := make([]SkillEntry, 0, count)
	for i := 0; i < count; i++ {
		name := fmt.Sprintf("test-skill-%d", i)
		path := filepath.Join(dir, name, "SKILL.md")
		os.MkdirAll(filepath.Dir(path), 0755)
		content := fmt.Sprintf("---\nname: %s\ndescription: skill %d\ntags: [test]\n---\n# Body\n", name, i)
		os.WriteFile(path, []byte(content), 0644)
		entries = append(entries, SkillEntry{
			Name:        name,
			Description: fmt.Sprintf("skill %d", i),
			Tags:        []string{"test"},
			Source:      "test",
			Path:        path,
			Checksum:    fmt.Sprintf("%x", sha256.Sum256([]byte(content))),
		})
	}
	return entries
}

func TestSaveAndLoadSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 3)
	if err := saveSnapshot(entries); err != nil {
		t.Fatalf("save: %v", err)
	}

	loaded, ok := loadSnapshot()
	if !ok {
		t.Fatal("load returned false")
	}
	if len(loaded) != 3 {
		t.Fatalf("expected 3 entries, got %d", len(loaded))
	}
	for i, e := range loaded {
		if e.Name != entries[i].Name {
			t.Errorf("entry[%d] name = %q, want %q", i, e.Name, entries[i].Name)
		}
	}
}

func TestSnapshotInvalidatesOnFileChange(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 2)
	if err := saveSnapshot(entries); err != nil {
		t.Fatalf("save: %v", err)
	}

	time.Sleep(10 * time.Millisecond)
	os.WriteFile(entries[0].Path, []byte("modified"), 0644)

	_, ok := loadSnapshot()
	if ok {
		t.Fatal("snapshot should be invalid after file modification")
	}
}

func TestSnapshotInvalidatesOnFileRemoval(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 2)
	if err := saveSnapshot(entries); err != nil {
		t.Fatalf("save: %v", err)
	}

	os.Remove(entries[0].Path)
	os.RemoveAll(filepath.Dir(entries[0].Path))

	_, ok := loadSnapshot()
	if ok {
		t.Fatal("snapshot should be invalid after file removal")
	}
}

func TestSnapshotLoadMissingFile(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	_, ok := loadSnapshot()
	if ok {
		t.Fatal("load should return false for missing snapshot")
	}
}

func TestClearSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 1)
	saveSnapshot(entries)

	if err := clearSnapshot(); err != nil {
		t.Fatalf("clear: %v", err)
	}

	_, ok := loadSnapshot()
	if ok {
		t.Fatal("snapshot should be gone after clear")
	}
}

func TestTryLoadIndexWithSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 5)
	saveSnapshot(entries)

	roots := []string{tmp}
	loaded, errs := tryLoadIndex(roots)
	if len(errs) > 0 {
		t.Fatalf("unexpected errors: %v", errs)
	}
	if len(loaded) != 5 {
		t.Fatalf("expected 5 entries, got %d", len(loaded))
	}
}

func TestTryLoadIndexFallbackToBuild(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeTestEntries(t, tmp, 3)

	roots := []string{tmp}
	loaded, errs := tryLoadIndex(roots)
	if len(errs) > 0 {
		t.Fatalf("unexpected errors: %v", errs)
	}
	if len(loaded) < 3 {
		t.Fatalf("expected at least 3 entries, got %d", len(loaded))
	}

	for _, want := range entries {
		found := false
		for _, got := range loaded {
			if got.Name == want.Name {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("missing entry: %s", want.Name)
		}
	}
}
