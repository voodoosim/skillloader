package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func buildTestIndex() []SkillEntry {
	return []SkillEntry{
		{
			Name:        "computer-use",
			Description: "Use Orca's computer-use CLI to inspect and operate local desktop app windows",
			Tags:        []string{"computer-use", "orca", "desktop", "accessibility"},
			Source:      "shared_agent",
			Path:        "/home/user/.agents/skills/computer-use/SKILL.md",
			Checksum:    "abc123",
		},
		{
			Name:        "orca-cli",
			Description: "Use the public orca CLI to operate Orca-managed worktrees and folders",
			Tags:        []string{"orca", "cli", "worktree", "terminal"},
			Source:      "shared_agent",
			Path:        "/home/user/.agents/skills/orca-cli/SKILL.md",
			Checksum:    "def456",
		},
		{
			Name:        "cloudflare-ops",
			Description: "Manage Cloudflare DNS, Workers, and Pages deployments",
			Tags:        []string{"cloudflare", "deploy", "ops", "dns"},
			Source:      "codex",
			Path:        "/home/user/.codex/skills/cloudflare-ops/SKILL.md",
			Checksum:    "ghi789",
		},
		{
			Name:        "orchestration",
			Description: "Use Orca orchestration for structured multi-agent coordination",
			Tags:        []string{"orchestration", "orca", "multi-agent", "coordinator"},
			Source:      "shared_agent",
			Path:        "/home/user/.agents/skills/orchestration/SKILL.md",
			Checksum:    "jkl012",
		},
		{
			Name:        "git-helper",
			Description: "Git workflow automation with branch management and rebase helpers",
			Tags:        []string{"git", "workflow", "branch", "rebase"},
			Source:      "claude",
			Path:        "/home/user/.claude/skills/git-helper/SKILL.md",
			Checksum:    "mno345",
		},
	}
}

func TestTokenize(t *testing.T) {
	tokens := tokenize("orca computer use desktop")
	if len(tokens) != 4 {
		t.Fatalf("expected 4 tokens, got %d: %v", len(tokens), tokens)
	}
	expected := []string{"orca", "computer", "use", "desktop"}
	for i, exp := range expected {
		if tokens[i] != exp {
			t.Errorf("token[%d] = %q, want %q", i, tokens[i], exp)
		}
	}
}

func TestTokenizeDedup(t *testing.T) {
	tokens := tokenize("orca orca ORCA desktop desktop")
	if len(tokens) != 2 {
		t.Fatalf("expected 2 unique tokens, got %d: %v", len(tokens), tokens)
	}
}

func TestTokenizeShortWords(t *testing.T) {
	tokens := tokenize("a b c orca")
	if len(tokens) != 1 || tokens[0] != "orca" {
		t.Errorf("short words should be filtered, got: %v", tokens)
	}
}

func TestSearchExactNameMatch(t *testing.T) {
	index := buildTestIndex()
	engine := NewSearchEngine(index)
	results := engine.Search("computer-use", 5)

	if len(results) == 0 {
		t.Fatal("expected at least one result")
	}
	if results[0].Name != "computer-use" {
		t.Errorf("top result = %q, want %q", results[0].Name, "computer-use")
	}
	if results[0].Score < 100 {
		t.Errorf("exact name match should score >= 100, got %d", results[0].Score)
	}
}

func TestSearchTagMatch(t *testing.T) {
	index := buildTestIndex()
	engine := NewSearchEngine(index)
	results := engine.Search("cloudflare deploy", 5)

	if len(results) == 0 {
		t.Fatal("expected at least one cloudflare result")
	}
	found := false
	for _, r := range results {
		if r.Name == "cloudflare-ops" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("cloudflare-ops not found in results")
	}
}

func TestSearchDescriptionMatch(t *testing.T) {
	index := buildTestIndex()
	engine := NewSearchEngine(index)
	results := engine.Search("orchestration for multi-agent", 5)

	if len(results) == 0 {
		t.Fatal("expected at least one result")
	}
	if results[0].Name != "orchestration" {
		t.Errorf("top result = %q, want %q", results[0].Name, "orchestration")
	}
}

func TestSearchResultLimit(t *testing.T) {
	index := buildTestIndex()
	engine := NewSearchEngine(index)
	results := engine.Search("orca", 2)

	if len(results) > 2 {
		t.Errorf("expected at most 2 results, got %d", len(results))
	}
}

func TestSearchSerialization(t *testing.T) {
	index := buildTestIndex()
	engine := NewSearchEngine(index)
	results := engine.Search("orca", 5)

	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	if !json.Valid(data) {
		t.Fatal("output is not valid JSON")
	}
	var parsed []SearchMatch
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if len(parsed) == 0 {
		t.Fatal("unmarshalled results are empty")
	}
}

func TestDedupRemovesDuplicates(t *testing.T) {
	entries := []scoredEntry{
		{entry: SkillEntry{Name: "alpha", Source: "codex"}, score: 80},
		{entry: SkillEntry{Name: "alpha", Source: "claude"}, score: 60},
		{entry: SkillEntry{Name: "beta", Source: "codex"}, score: 50},
	}
	result := layerDedup(entries)
	if len(result) != 2 {
		t.Fatalf("expected 2 after dedup, got %d", len(result))
	}
	if result[0].score != 80 {
		t.Errorf("dedup kept lower score for alpha: %d", result[0].score)
	}
}

func TestSafetyFilterRejectsNameless(t *testing.T) {
	entries := []scoredEntry{
		{entry: SkillEntry{Name: "", Path: "/x", Source: "codex"}, score: 10},
		{entry: SkillEntry{Name: "valid", Path: "/y", Source: "codex"}, score: 10},
	}
	result := layerSafetyFilter(entries)
	if len(result) != 1 {
		t.Fatalf("expected 1 after safety filter, got %d", len(result))
	}
}

func TestParseFrontmatterValid(t *testing.T) {
	input := `---
name: test-skill
description: "a test skill"
tags: [tag1, tag2, tag3]
---
`

	fm, err := parseFrontmatter(input)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if fm["name"] != "test-skill" {
		t.Errorf("name = %q, want %q", fm["name"], "test-skill")
	}
	if fm["description"] != "a test skill" {
		t.Errorf("description = %q, want %q", fm["description"], "a test skill")
	}
	if fm["tags"] != "[tag1, tag2, tag3]" {
		t.Errorf("tags = %q", fm["tags"])
	}
}

func TestParseFrontmatterMissingDelimiter(t *testing.T) {
	input := `# No frontmatter here
`

	fm, err := parseFrontmatter(input)
	if err == nil {
		t.Fatal("expected error for missing frontmatter, got nil")
	}
	if fm != nil {
		t.Errorf("expected nil map on error, got %v", fm)
	}
}

func TestParseTagList(t *testing.T) {
	tests := []struct {
		raw  string
		want []string
	}{
		{"[tag1, tag2, tag3]", []string{"tag1", "tag2", "tag3"}},
		{"[tag1, #tag2]", []string{"tag1", "tag2"}},
		{"tag1, tag2", []string{"tag1", "tag2"}},
		{"", nil},
	}

	for _, tt := range tests {
		got := parseTagList(tt.raw)
		if len(got) != len(tt.want) {
			t.Errorf("parseTagList(%q) = %v, want %v", tt.raw, got, tt.want)
			continue
		}
		for i := range got {
			if got[i] != tt.want[i] {
				t.Errorf("parseTagList(%q)[%d] = %q, want %q", tt.raw, i, got[i], tt.want[i])
			}
		}
	}
}

func TestClassifySource(t *testing.T) {
	tests := []struct {
		path string
		want string
	}{
		{"/home/user/.codex/skills/foo/SKILL.md", "codex"},
		{"/home/user/.codex/skills/.system/bar/SKILL.md", "system"},
		{"/home/user/.codex/disabled-skills/old/SKILL.md", "disabled"},
		{"/home/user/.agents/skills/shared/SKILL.md", "shared_agent"},
		{"/home/user/.claude/skills/claude/SKILL.md", "claude"},
		{"/tmp/other/SKILL.md", "other"},
	}

	for _, tt := range tests {
		got := classifySource(tt.path)
		if got != tt.want {
			t.Errorf("classifySource(%q) = %q, want %q", tt.path, got, tt.want)
		}
	}
}

func TestCleanName(t *testing.T) {
	if cleanName("  foo  ") != "foo" {
		t.Errorf("cleanName with spaces failed")
	}
	if cleanName("") != "" {
		t.Errorf("cleanName(\"\") should be empty")
	}
}

func TestDiscoverSkillsCreatesRealIndex(t *testing.T) {
	tmp := t.TempDir()
	skillDir := filepath.Join(tmp, "test-skill")
	if err := os.MkdirAll(skillDir, 0755); err != nil {
		t.Fatal(err)
	}
	content := `---
name: test-discover
description: "discovery test"
tags: [test, discovery]
---

# Test Skill

This is a test skill for discovery.
`
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	roots := []string{tmp}
	paths, err := DiscoverSkills(roots)
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 1 {
		t.Fatalf("expected 1 discovered path, got %d", len(paths))
	}

	entries, errs, err := BuildIndex(roots)
	if err != nil {
		t.Fatal(err)
	}
	if len(errs) > 0 {
		for _, e := range errs {
			t.Logf("build err: %s", e)
		}
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(entries))
	}
	if entries[0].Name != "test-discover" {
		t.Errorf("name = %q", entries[0].Name)
	}
	if entries[0].Checksum == "" {
		t.Error("checksum is empty")
	}
}
