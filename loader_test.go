package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoaderLoadByName(t *testing.T) {
	tmp := t.TempDir()
	skillDir := filepath.Join(tmp, "test-skill")
	os.MkdirAll(skillDir, 0755)

	content := `---
name: test-loader
description: "a test skill"
tags: [test, loader]
---

# Test Skill

Body content here.
`
	skillPath := filepath.Join(skillDir, "SKILL.md")
	if err := os.WriteFile(skillPath, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	index := []SkillEntry{{
		Name:        "test-loader",
		Description: "a test skill",
		Tags:        []string{"test", "loader"},
		Source:      "test",
		Path:        skillPath,
		Checksum:    fmt.Sprintf("%x", sha256.Sum256([]byte(content))),
	}}

	cache := NewCache()
	loader := NewSkillLoader(index, []string{tmp}, cache)

	result, err := loader.Load("test-loader")
	if err != nil {
		t.Fatalf("load failed: %v", err)
	}
	if result.Name != "test-loader" {
		t.Errorf("name = %q", result.Name)
	}
	if !strings.Contains(result.Content, "# Test Skill") {
		t.Errorf("content missing body: %s", result.Content)
	}
	if result.ContentSHA != index[0].Checksum {
		t.Errorf("content SHA = %q", result.ContentSHA)
	}
}

func TestLoaderNotFound(t *testing.T) {
	loader := NewSkillLoader(nil, nil, NewCache())
	_, err := loader.Load("nonexistent")
	if err == nil {
		t.Fatal("expected error for missing skill")
	}
	if !strings.Contains(err.Error(), "SKILL_NOT_FOUND") {
		t.Errorf("error should say SKILL_NOT_FOUND, got: %v", err)
	}
}

func TestLoaderAmbiguousName(t *testing.T) {
	index := []SkillEntry{
		{Name: "dupe", Source: "codex", Path: "/a/SKILL.md"},
		{Name: "dupe", Source: "claude", Path: "/b/SKILL.md"},
	}
	loader := NewSkillLoader(index, nil, NewCache())
	_, err := loader.Load("dupe")
	if err == nil {
		t.Fatal("expected error for ambiguous name")
	}
	if !strings.Contains(err.Error(), "AMBIGUOUS_SKILL") {
		t.Errorf("error should say AMBIGUOUS_SKILL, got: %v", err)
	}
}

func TestLoaderRejectsTraversal(t *testing.T) {
	loader := NewSkillLoader([]SkillEntry{
		{Name: "escape", Source: "codex",
			Path: "/home/vodo/../../../etc/passwd"},
	}, []string{"/home/vodo"}, NewCache())
	_, err := loader.Load("escape")
	if err == nil {
		t.Fatal("expected error for traversal path")
	}
	if !strings.Contains(err.Error(), "UNSAFE_SOURCE") && !strings.Contains(err.Error(), "traversal") {
		t.Errorf("error should mention UNSAFE_SOURCE or traversal, got: %v", err)
	}
}

func TestCacheStoreAndGet(t *testing.T) {
	c := NewCache()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "skill.md")
	content := "cached content"
	os.WriteFile(path, []byte(content), 0644)

	c.SetDocument(path, content, "v1")
	got, ok := c.GetDocument(path, "v1")
	if !ok {
		t.Fatal("cache miss after SetDocument")
	}
	if got != content {
		t.Errorf("cache returned %q, want %q", got, content)
	}
}

func TestCacheInvalidatesOnChange(t *testing.T) {
	c := NewCache()

	tmp := t.TempDir()
	path := filepath.Join(tmp, "skill.md")
	os.WriteFile(path, []byte("v1"), 0644)

	c.SetDocument(path, "v1", "checksum-v1")
	os.WriteFile(path, []byte("v2"), 0644)

	_, ok := c.GetDocument(path, "checksum-v2")
	if ok {
		t.Fatal("cache should invalidate when file changes")
	}
}

func TestCacheStoreIndex(t *testing.T) {
	c := NewCache()
	entries := []SkillEntry{
		{Name: "a", Checksum: "aaaa"},
		{Name: "b", Checksum: "bbbb"},
	}
	c.StoreIndex(entries)
	loaded := c.LoadIndex()
	if len(loaded) != 2 {
		t.Fatalf("expected 2 entries, got %d", len(loaded))
	}
	if loaded[0].Name != "a" {
		t.Errorf("unexpected order: %v", loaded)
	}
}

func TestCacheInvalidateAll(t *testing.T) {
	c := NewCache()
	tmp := t.TempDir()
	path := filepath.Join(tmp, "skill.md")
	os.WriteFile(path, []byte("test"), 0644)
	c.SetDocument(path, "test", "checksum")
	c.InvalidateAll()
	if c.DocCount() != 0 {
		t.Errorf("expected 0 docs after invalidate, got %d", c.DocCount())
	}
	if c.LoadIndex() != nil {
		t.Error("expected nil index after invalidate")
	}
}

func TestLoaderRejectsSymlinkEscape(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	outsidePath := filepath.Join(outside, "SKILL.md")
	if err := os.WriteFile(outsidePath, []byte("---\nname: escaped\n---\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	linkPath := filepath.Join(root, "SKILL.md")
	if err := os.Symlink(outsidePath, linkPath); err != nil {
		t.Fatal(err)
	}

	loader := NewSkillLoader([]SkillEntry{{Name: "escaped", Path: linkPath}}, []string{root}, NewCache())
	_, err := loader.Load("escaped")
	if err == nil {
		t.Fatal("expected symlink escape to be rejected")
	}
	if !strings.Contains(err.Error(), "UNSAFE_SOURCE") {
		t.Fatalf("symlink escape error = %v, want UNSAFE_SOURCE", err)
	}
	if strings.Contains(err.Error(), root) || strings.Contains(err.Error(), outside) {
		t.Fatalf("symlink escape error leaked a path: %v", err)
	}
}

func TestLoaderRejectsDirectPathOutsideTrustedRoot(t *testing.T) {
	root := t.TempDir()
	outside := filepath.Join(t.TempDir(), "SKILL.md")
	if err := os.WriteFile(outside, []byte("---\nname: outside\n---\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	loader := NewSkillLoader([]SkillEntry{{Name: "outside", Path: outside}}, []string{root}, NewCache())
	_, err := loader.Load("outside")
	if err == nil || !strings.Contains(err.Error(), "UNSAFE_SOURCE") {
		t.Fatalf("outside path error = %v, want UNSAFE_SOURCE", err)
	}
}

func TestLoaderReturnsChecksumForCurrentContent(t *testing.T) {
	tmp := t.TempDir()
	path := filepath.Join(tmp, "SKILL.md")
	initial := []byte("---\nname: changing\n---\nv1\n")
	current := []byte("---\nname: changing\n---\nv2\n")
	if err := os.WriteFile(path, initial, 0o644); err != nil {
		t.Fatal(err)
	}
	oldChecksum := fmt.Sprintf("%x", sha256.Sum256(initial))
	if err := os.WriteFile(path, current, 0o644); err != nil {
		t.Fatal(err)
	}

	loader := NewSkillLoader([]SkillEntry{{
		Name: "changing", Path: path, Checksum: oldChecksum,
	}}, []string{tmp}, NewCache())
	result, err := loader.Load("changing")
	if err != nil {
		t.Fatal(err)
	}
	want := fmt.Sprintf("%x", sha256.Sum256(current))
	if result.ContentSHA != want {
		t.Fatalf("content SHA = %q, want current checksum %q", result.ContentSHA, want)
	}
}

func TestLoaderDoesNotReturnCachedContentAfterRemoval(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "SKILL.md")
	content := []byte("---\nname: removable\n---\nbody\n")
	if err := os.WriteFile(path, content, 0o644); err != nil {
		t.Fatal(err)
	}
	loader := NewSkillLoader([]SkillEntry{{Name: "removable", Path: path}}, []string{root}, NewCache())
	if _, err := loader.Load("removable"); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if _, err := loader.Load("removable"); err == nil || !strings.Contains(err.Error(), "INVALID_SKILL") {
		t.Fatalf("removed document error = %v, want INVALID_SKILL", err)
	}
}
