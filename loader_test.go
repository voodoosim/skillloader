package main

import (
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
		Checksum:    "dummy",
	}}

	cache := NewCache()
	loader := NewSkillLoader(index, cache)

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
	if result.ContentSHA != "dummy" {
		t.Errorf("content SHA = %q", result.ContentSHA)
	}
}

func TestLoaderNotFound(t *testing.T) {
	loader := NewSkillLoader(nil, NewCache())
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
	loader := NewSkillLoader(index, NewCache())
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
	}, NewCache())
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

	c.SetDocument(path, content)
	got, ok := c.GetDocument(path)
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

	c.SetDocument(path, "v1")
	os.WriteFile(path, []byte("v2"), 0644)

	_, ok := c.GetDocument(path)
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
	c.SetDocument(path, "test")
	c.InvalidateAll()
	if c.DocCount() != 0 {
		t.Errorf("expected 0 docs after invalidate, got %d", c.DocCount())
	}
	if c.LoadIndex() != nil {
		t.Error("expected nil index after invalidate")
	}
}

func TestLoaderValidatePath(t *testing.T) {
	tests := []struct {
		path    string
		wantErr bool
	}{
		{"/nonexistent/path/skill.md", true}, // EvalSymlinks fails on non-existent
		{"/home/vodo/../../../etc/passwd", true},
	}

	for _, tt := range tests {
		err := validatePath(tt.path)
		if (err != nil) != tt.wantErr {
			t.Errorf("validatePath(%q) error=%v, wantErr=%v", tt.path, err, tt.wantErr)
		}
	}
}
