package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func makeSnapshotTestEntries(t *testing.T, dir string, count int) []SkillEntry {
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
			Checksum:    fmt.Sprintf("%x", sumContent(content)),
		})
	}
	return entries
}

func sumContent(s string) [32]byte {
	h := [32]byte{}
	copy(h[:], []byte(s))
	return h
}

func TestSaveAndLoadSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 3)
	roots := []string{tmp}
	if err := saveSnapshot(entries, nil, roots); err != nil {
		t.Fatalf("save: %v", err)
	}

	loaded, errs, ok := loadSnapshot(roots)
	if !ok {
		t.Fatal("load returned false")
	}
	if len(errs) > 0 {
		t.Errorf("unexpected errors: %v", errs)
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

func TestSnapshotInvalidatesOnRootsChange(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 3)
	saveSnapshot(entries, nil, []string{tmp})

	otherRoot := filepath.Join(tmp, "other")
	os.MkdirAll(otherRoot, 0755)
	_, _, ok := loadSnapshot([]string{otherRoot})
	if ok {
		t.Fatal("snapshot should be invalid when roots change")
	}
}

func TestSnapshotInvalidatesOnNewFile(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 2)
	roots := []string{tmp}
	saveSnapshot(entries, nil, roots)

	newDir := filepath.Join(tmp, "new-skill")
	os.MkdirAll(newDir, 0755)
	os.WriteFile(filepath.Join(newDir, "SKILL.md"),
		[]byte("---\nname: new-skill\ndescription: new\ntags: [new]\n---\n# Body\n"), 0644)

	_, _, ok := loadSnapshot(roots)
	if ok {
		t.Fatal("snapshot should be invalid when new SKILL.md added")
	}
}

func TestSnapshotInvalidatesOnFileChange(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 2)
	roots := []string{tmp}
	if err := saveSnapshot(entries, nil, roots); err != nil {
		t.Fatalf("save: %v", err)
	}

	future := time.Now().Add(time.Hour)
	os.Chtimes(entries[0].Path, future, future)

	_, _, ok := loadSnapshot(roots)
	if ok {
		t.Fatal("snapshot should be invalid after mtime change")
	}
}

func TestSnapshotInvalidatesOnFileRemoval(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 2)
	roots := []string{tmp}
	if err := saveSnapshot(entries, nil, roots); err != nil {
		t.Fatalf("save: %v", err)
	}

	os.Remove(entries[0].Path)

	_, _, ok := loadSnapshot(roots)
	if ok {
		t.Fatal("snapshot should be invalid after file removal")
	}
}

func TestSnapshotPreservesErrors(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 1)
	roots := []string{tmp}
	fakeErrs := []string{"warn: something", "err: missing tags"}

	saveSnapshot(entries, fakeErrs, roots)

	_, errs, ok := loadSnapshot(roots)
	if !ok {
		t.Fatal("load returned false")
	}
	if len(errs) != 2 {
		t.Fatalf("expected 2 errors, got %d: %v", len(errs), errs)
	}
	if errs[0] != "warn: something" {
		t.Errorf("errs[0] = %q", errs[0])
	}
}

func TestSnapshotLoadMissingFile(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	_, _, ok := loadSnapshot([]string{tmp})
	if ok {
		t.Fatal("load should return false for missing snapshot")
	}
}

func TestClearSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 1)
	roots := []string{tmp}
	saveSnapshot(entries, nil, roots)

	if err := clearSnapshot(); err != nil {
		t.Fatalf("clear: %v", err)
	}

	_, _, ok := loadSnapshot(roots)
	if ok {
		t.Fatal("snapshot should be gone after clear")
	}
}

func TestTryLoadIndexWithSnapshot(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("XDG_CACHE_HOME", tmp)

	entries := makeSnapshotTestEntries(t, tmp, 5)
	roots := []string{tmp}
	saveSnapshot(entries, nil, roots)

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

	entries := makeSnapshotTestEntries(t, tmp, 3)

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
