package main

import (
	"errors"
	"strings"
)

// SkillLoader resolves logical names to file paths, validates safety, and
// returns complete skill document content.
type SkillLoader struct {
	index []SkillEntry
	roots []string
	cache *Cache
}

// NewSkillLoader builds a loader from the catalog index.
func NewSkillLoader(index []SkillEntry, roots []string, cache *Cache) *SkillLoader {
	return &SkillLoader{index: index, roots: append([]string{}, roots...), cache: cache}
}

// SkillError is a stable, redacted application error returned by load_skill.
type SkillError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

func (e *SkillError) Error() string { return e.Code + ": " + e.Message }

// LoadResult is the validated output of a load operation.
type LoadResult struct {
	Name       string `json:"name"`
	Content    string `json:"content"`
	Source     string `json:"source"`
	ContentSHA string `json:"content_sha256"`
}

// Load resolves a logical skill name to a file, validates it, and returns the
// complete content. Namespace prefixes (plugin:name) are stripped before
// lookup in the non-plugin index. Returns an error for missing, ambiguous,
// unsafe, or invalid skills.
func (l *SkillLoader) Load(name string) (*LoadResult, error) {
	name = cleanName(name)
	if name == "" {
		return nil, skillError("INVALID_ARGUMENT", "A non-empty logical skill name is required.")
	}

	candidates := l.lookup(name)
	if len(candidates) == 0 {
		return nil, skillError("SKILL_NOT_FOUND", "The logical skill name was not found.")
	}
	if len(candidates) > 1 {
		return nil, skillError("AMBIGUOUS_SKILL", "The logical skill name resolves to multiple trusted sources.")
	}

	entry := candidates[0]
	path := entry.Path

	data, err := readTrustedFile(l.roots, path)
	if err != nil {
		if errors.Is(err, errOutsideTrustedRoots) {
			return nil, skillError("UNSAFE_SOURCE", "The skill source is outside its configured trusted root.")
		}
		return nil, skillError("INVALID_SKILL", "The selected skill document cannot be read.")
	}
	checksum := hexSHA256(data)

	if cached, ok := l.cache.GetDocument(path, checksum); ok {
		return &LoadResult{
			Name:       entry.Name,
			Content:    cached,
			Source:     entry.Source,
			ContentSHA: checksum,
		}, nil
	}

	content := string(data)
	fm, err := parseFrontmatter(content)
	if err != nil || fm["name"] == "" || fm["name"] != entry.Name {
		return nil, skillError("INVALID_SKILL", "The selected skill document has invalid or changed metadata.")
	}

	l.cache.SetDocument(path, content, checksum)

	return &LoadResult{
		Name:       entry.Name,
		Content:    content,
		Source:     entry.Source,
		ContentSHA: checksum,
	}, nil
}

func skillError(code, message string) *SkillError {
	return &SkillError{Code: code, Message: message, Retryable: false}
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
