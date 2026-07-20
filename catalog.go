package main

import (
	"crypto/sha256"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// SkillEntry is a compact metadata record for one discovered skill.
type SkillEntry struct {
	Name        string
	Description string
	Tags        []string
	Source      string // logical source label
	Path        string // absolute filesystem path
	Checksum    string // sha256 of file content
}

// DefaultRoots returns the standard skill catalog roots on this machine.
func DefaultRoots() []string {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil
	}
	return []string{
		filepath.Join(home, ".codex", "skills"),
		filepath.Join(home, ".codex", "disabled-skills"),
		filepath.Join(home, ".agents", "skills"),
		filepath.Join(home, ".claude", "skills"),
	}
}

// DiscoverSkills walks the configured roots and returns every SKILL.md path.
func DiscoverSkills(roots []string) ([]string, error) {
	var paths []string
	seen := make(map[string]struct{})

	for _, root := range roots {
		info, err := os.Stat(root)
		if err != nil {
			continue
		}
		if info.IsDir() {
			_ = filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
				if err != nil {
					return nil
				}
				if d.Name() == "SKILL.md" && d.Type().IsRegular() {
					abs, _ := filepath.Abs(p)
					if _, ok := seen[abs]; !ok {
						seen[abs] = struct{}{}
						paths = append(paths, abs)
					}
				}
				return nil
			})
		}
	}

	sort.Strings(paths)
	return paths, nil
}

// ParseSkill reads a SKILL.md file and extracts frontmatter metadata.
func ParseSkill(path string) (SkillEntry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return SkillEntry{}, fmt.Errorf("read %s: %w", path, err)
	}

	hash := fmt.Sprintf("%x", sha256.Sum256(data))
	fm, err := parseFrontmatter(string(data))
	if err != nil {
		return SkillEntry{}, fmt.Errorf("parse %s: %w", path, err)
	}

	name := fm["name"]
	desc := fm["description"]
	source := classifySource(path)
	tags := parseTagList(fm["tags"])

	if name == "" {
		return SkillEntry{}, fmt.Errorf("parse %s: missing name in frontmatter", path)
	}

	return SkillEntry{
		Name:        name,
		Description: desc,
		Tags:        tags,
		Source:      source,
		Path:        path,
		Checksum:    hash,
	}, nil
}

// BuildIndex discovers and parses all skills, returning the catalog index.
func BuildIndex(roots []string) ([]SkillEntry, []string, error) {
	paths, err := DiscoverSkills(roots)
	if err != nil {
		return nil, nil, err
	}

	var entries []SkillEntry
	var errors []string
	for _, p := range paths {
		entry, err := ParseSkill(p)
		if err != nil {
			errors = append(errors, err.Error())
			continue
		}
		entries = append(entries, entry)
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name < entries[j].Name
	})

	return entries, errors, nil
}

// ---------------------------------------------------------------------------
// Frontmatter parser
// ---------------------------------------------------------------------------

func parseFrontmatter(text string) (map[string]string, error) {
	lines := strings.Split(text, "\n")
	if len(lines) == 0 || strings.TrimSpace(lines[0]) != "---" {
		return nil, fmt.Errorf("missing opening frontmatter delimiter")
	}

	end := -1
	for i := 1; i < len(lines); i++ {
		if strings.TrimSpace(lines[i]) == "---" {
			end = i
			break
		}
	}
	if end == -1 {
		return nil, fmt.Errorf("missing closing frontmatter delimiter")
	}

	fm := make(map[string]string)
	for i := 1; i < end; i++ {
		line := lines[i]
		parts := strings.SplitN(line, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		val = strings.Trim(val, "\"'")
		fm[key] = val
	}
	return fm, nil
}

func parseTagList(raw string) []string {
	if raw == "" {
		return nil
	}

	raw = strings.Trim(raw, "[]")
	parts := strings.Split(raw, ",")
	var tags []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		p = strings.Trim(p, "\"'")
		p = strings.TrimPrefix(p, "#")
		if p != "" {
			tags = append(tags, p)
		}
	}
	return tags
}

func classifySource(path string) string {
	switch {
	case strings.Contains(path, "/.codex/skills/.system"):
		return "system"
	case strings.Contains(path, "/.codex/disabled-skills"):
		return "disabled"
	case strings.Contains(path, "/.agents/skills"):
		return "shared_agent"
	case strings.Contains(path, "/.claude/skills"):
		return "claude"
	case strings.Contains(path, "/.codex/skills"):
		return "codex"
	default:
		return "other"
	}
}
