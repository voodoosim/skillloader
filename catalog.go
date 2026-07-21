package main

import (
	"crypto/sha256"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"go.yaml.in/yaml/v3"
)

var (
	errOutsideTrustedRoots = errors.New("outside configured trusted roots")
	errUnreadableSkill     = errors.New("trusted skill is unreadable")
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
		absRoot, err := filepath.Abs(root)
		if err != nil {
			continue
		}
		trustedRoot, err := os.OpenRoot(absRoot)
		if err != nil {
			continue
		}
		_ = fs.WalkDir(trustedRoot.FS(), ".", func(rel string, d fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return nil
			}
			if d.Name() == "SKILL.md" && d.Type().IsRegular() {
				path := filepath.Join(absRoot, filepath.FromSlash(rel))
				if _, ok := seen[path]; !ok {
					seen[path] = struct{}{}
					paths = append(paths, path)
				}
			}
			return nil
		})
		if err := trustedRoot.Close(); err != nil {
			return paths, err
		}
	}

	sort.Strings(paths)
	return paths, nil
}

// ParseSkill reads a SKILL.md file and extracts frontmatter metadata.
func ParseSkill(path string, roots []string) (SkillEntry, error) {
	data, err := readTrustedFile(roots, path)
	if err != nil {
		return SkillEntry{}, err
	}
	return parseSkillData(path, data)
}

func hexSHA256(data []byte) string {
	return fmt.Sprintf("%x", sha256.Sum256(data))
}

func parseSkillData(path string, data []byte) (SkillEntry, error) {
	hash := hexSHA256(data)
	fm, err := parseFrontmatter(string(data))
	if err != nil {
		return SkillEntry{}, fmt.Errorf("invalid frontmatter: %w", err)
	}

	name := fm["name"]
	desc := fm["description"]
	source := classifySource(path)
	tags := parseTagList(fm["tags"])

	if name == "" {
		return SkillEntry{}, fmt.Errorf("invalid frontmatter: missing name")
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
	for i, p := range paths {
		entry, err := ParseSkill(p, roots)
		if err != nil {
			errors = append(errors, fmt.Sprintf("skill[%d]: %s", i, redactedCatalogError(err)))
			continue
		}
		entries = append(entries, entry)
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name < entries[j].Name
	})

	return entries, errors, nil
}

func tryLoadIndex(roots []string) ([]SkillEntry, []string) {
	if entries, errs, ok := loadSnapshot(roots); ok {
		return entries, errs
	}

	entries, errs, err := BuildIndex(roots)
	if err != nil {
		return nil, []string{err.Error()}
	}

	_ = saveSnapshot(entries, errs, roots)
	return entries, errs
}

func redactedCatalogError(err error) string {
	switch {
	case errors.Is(err, errOutsideTrustedRoots):
		return "source escapes its trusted root"
	case errors.Is(err, errUnreadableSkill):
		return "document is unreadable"
	default:
		return err.Error()
	}
}

func readTrustedFile(roots []string, path string) ([]byte, error) {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, errOutsideTrustedRoots
	}

	for _, configuredRoot := range roots {
		absRoot, err := filepath.Abs(configuredRoot)
		if err != nil {
			continue
		}
		rel, err := filepath.Rel(absRoot, absPath)
		if err != nil || rel == "." || filepath.IsAbs(rel) || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			continue
		}

		resolvedRoot, err := filepath.EvalSymlinks(absRoot)
		if err != nil {
			return nil, errUnreadableSkill
		}
		resolvedPath, err := filepath.EvalSymlinks(absPath)
		if err != nil {
			if errors.Is(err, os.ErrNotExist) {
				return nil, errUnreadableSkill
			}
			return nil, errOutsideTrustedRoots
		}
		if !pathWithinRoot(resolvedRoot, resolvedPath) {
			return nil, errOutsideTrustedRoots
		}

		trustedRoot, err := os.OpenRoot(absRoot)
		if err != nil {
			return nil, errUnreadableSkill
		}
		data, readErr := trustedRoot.ReadFile(rel)
		_ = trustedRoot.Close()
		if readErr != nil {
			if errors.Is(readErr, os.ErrNotExist) {
				return nil, errUnreadableSkill
			}
			return nil, errOutsideTrustedRoots
		}
		return data, nil
	}

	return nil, errOutsideTrustedRoots
}

func pathWithinRoot(root, path string) bool {
	rel, err := filepath.Rel(root, path)
	return err == nil && rel != "." && !filepath.IsAbs(rel) && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}

// ---------------------------------------------------------------------------
// Frontmatter parser
// ---------------------------------------------------------------------------

func parseFrontmatter(text string) (map[string]string, error) {
	lines := strings.Split(text, "\n")
	if len(lines) == 0 || strings.TrimSuffix(lines[0], "\r") != "---" {
		return nil, fmt.Errorf("missing opening frontmatter delimiter")
	}

	end := -1
	for i := 1; i < len(lines); i++ {
		if strings.TrimSuffix(lines[i], "\r") == "---" {
			end = i
			break
		}
	}
	if end == -1 {
		return nil, fmt.Errorf("missing closing frontmatter delimiter")
	}

	var raw struct {
		Name        any `yaml:"name"`
		Description any `yaml:"description"`
		Tags        any `yaml:"tags"`
	}
	if err := yaml.Unmarshal([]byte(strings.Join(lines[1:end], "\n")), &raw); err != nil {
		return nil, fmt.Errorf("invalid YAML: %w", err)
	}

	fm := map[string]string{
		"name":        normalizeYAMLString(raw.Name),
		"description": normalizeYAMLString(raw.Description),
	}
	tags, err := normalizeYAMLTags(raw.Tags)
	if err != nil {
		return nil, err
	}
	if len(tags) > 0 {
		fm["tags"] = "[" + strings.Join(tags, ", ") + "]"
	}
	return fm, nil
}

func normalizeYAMLTags(value any) ([]string, error) {
	switch tags := value.(type) {
	case nil:
		return nil, nil
	case string:
		return parseTagList(tags), nil
	case []any:
		out := make([]string, 0, len(tags))
		for _, item := range tags {
			tag, ok := item.(string)
			if !ok {
				return nil, fmt.Errorf("invalid frontmatter: tags must contain strings")
			}
			tag = strings.TrimSpace(strings.TrimPrefix(tag, "#"))
			if tag != "" {
				out = append(out, tag)
			}
		}
		return out, nil
	default:
		return nil, fmt.Errorf("invalid frontmatter: tags must be a string or list")
	}
}

func normalizeYAMLString(value any) string {
	if value == nil {
		return ""
	}
	switch v := value.(type) {
	case string:
		return v
	case []any:
		parts := make([]string, 0, len(v))
		for _, item := range v {
			if s, ok := item.(string); ok {
				parts = append(parts, s)
			}
		}
		return strings.Join(parts, ", ")
	default:
		return fmt.Sprintf("%v", v)
	}
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
