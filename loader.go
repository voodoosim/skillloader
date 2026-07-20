package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// SkillLoader resolves logical names to file paths, validates safety, and
// returns complete skill document content.
type SkillLoader struct {
	index []SkillEntry
	cache *Cache
}

// NewSkillLoader builds a loader from the catalog index.
func NewSkillLoader(index []SkillEntry, cache *Cache) *SkillLoader {
	return &SkillLoader{index: index, cache: cache}
}

// LoadResult is the validated output of a load operation.
type LoadResult struct {
	Name        string `json:"name"`
	Content     string `json:"content"`
	Source      string `json:"source"`
	ContentSHA  string `json:"content_sha256"`
}

// Load resolves a logical skill name to a file, validates it, and returns the
// complete content. Namespace prefixes (plugin:name) are stripped before
// lookup in the non-plugin index. Returns an error for missing, ambiguous,
// unsafe, or invalid skills.
func (l *SkillLoader) Load(name string) (*LoadResult, error) {
	name = cleanName(name)
	if name == "" {
		return nil, fmt.Errorf("INVALID_ARGUMENT: empty skill name")
	}

	candidates := l.lookup(name)
	if len(candidates) == 0 {
		return nil, fmt.Errorf("SKILL_NOT_FOUND: %s", name)
	}
	if len(candidates) > 1 {
		sources := make([]string, len(candidates))
		for i, c := range candidates {
			sources[i] = c.Source
		}
		return nil, fmt.Errorf("AMBIGUOUS_SKILL: %s resolves to multiple sources: %s",
			name, strings.Join(sources, ", "))
	}

	entry := candidates[0]
	path := entry.Path

	if err := validatePath(path); err != nil {
		return nil, fmt.Errorf("UNSAFE_SOURCE: %s: %w", path, err)
	}

	if cached, ok := l.cache.GetDocument(path); ok {
		return &LoadResult{
			Name:       entry.Name,
			Content:    cached,
			Source:     entry.Source,
			ContentSHA: entry.Checksum,
		}, nil
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("INVALID_SKILL: cannot read %s: %w", path, err)
	}

	content := string(data)
	if !strings.HasPrefix(strings.TrimSpace(content), "---") {
		return nil, fmt.Errorf("INVALID_SKILL: %s: missing frontmatter", path)
	}

	l.cache.SetDocument(path, content)

	return &LoadResult{
		Name:       entry.Name,
		Content:    content,
		Source:     entry.Source,
		ContentSHA: entry.Checksum,
	}, nil
}

func (l *SkillLoader) lookup(name string) []SkillEntry {
	var matches []SkillEntry
	for _, e := range l.index {
		if e.Name == name || strings.HasSuffix(e.Name, ":"+name) {
			matches = append(matches, e)
		}
	}
	return matches
}

func cleanName(name string) string {
	return strings.TrimSpace(name)
}

func validatePath(path string) error {
	if containsTraversal(path) {
		return fmt.Errorf("path traversal detected: %s", path)
	}

	abs, err := filepath.Abs(path)
	if err != nil {
		return fmt.Errorf("cannot resolve absolute path")
	}

	real, err := filepath.EvalSymlinks(abs)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("file does not exist")
		}
		return fmt.Errorf("cannot resolve path")
	}

	if containsTraversal(real) {
		return fmt.Errorf("path traversal detected after symlink resolution: %s", real)
	}

	return nil
}

func containsTraversal(path string) bool {
	for _, part := range strings.Split(path, string(filepath.Separator)) {
		if part == ".." {
			return true
		}
	}
	return false
}
