package main

import (
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

// SearchEngine runs the 8-layer deterministic ranking pipeline.
type SearchEngine struct {
	index []SkillEntry
}

// Ranking weights are deterministic prototype defaults. They have not been
// tuned against a frozen relevance fixture or benchmark.
const (
	tagMatchScore         = 8
	exactNameMatchScore   = 100
	partialNameMatchScore = 20
	descriptionMatchScore = 5
	tagOnlyBonus          = 4
)

// NewSearchEngine returns an engine backed by the given catalog index.
func NewSearchEngine(index []SkillEntry) *SearchEngine {
	return &SearchEngine{index: index}
}

// SearchMatch is one bounded result returned to the model.
type SearchMatch struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Tags        []string `json:"tags"`
	Source      string   `json:"source"`
	Score       int      `json:"score"`
}

// Search runs all eight layers and returns at most limit results.
func (e *SearchEngine) Search(query string, limit int) []SearchMatch {
	if limit <= 0 {
		limit = 5
	}

	// Layer 1: Tokenize query into normalized tokens.
	tokens := tokenize(query)

	// Layer 2: Tag matching — score each entry by tag overlap.
	tagScores := layerTagMatch(tokens, e.index)

	// Layer 3: Name matching — score by name substring presence.
	nameScores := layerNameMatch(tokens, e.index)

	// Layer 4: Description matching — score by description keyword hit.
	descScores := layerDescriptionMatch(tokens, e.index)

	// Layer 5: Aggregate scores and sort deterministic.
	scored := layerAggregate(e.index, tagScores, nameScores, descScores)
	sort.Slice(scored, func(i, j int) bool {
		if scored[i].score != scored[j].score {
			return scored[i].score > scored[j].score
		}
		return scored[i].entry.Name < scored[j].entry.Name
	})

	// Layer 6: Deduplicate by logical name (keep highest score).
	scored = layerDedup(scored)

	// Layer 7: Safety filter — remove entries with invalid metadata.
	scored = layerSafetyFilter(scored)

	// Layer 8: Limit results.
	if len(scored) > limit {
		scored = scored[:limit]
	}

	matches := make([]SearchMatch, 0, len(scored))
	for _, s := range scored {
		tags := s.entry.Tags
		if tags == nil {
			tags = []string{}
		}
		matches = append(matches, SearchMatch{
			Name:        s.entry.Name,
			Description: s.entry.Description,
			Tags:        tags,
			Source:      s.entry.Source,
			Score:       s.score,
		})
	}
	return matches
}

// ---------------------------------------------------------------------------
// Layer 1: Query tokenization
// ---------------------------------------------------------------------------

var tokenPattern = regexp.MustCompile(`[0-9a-zA-Z가-힣\-]+`)

func tokenize(query string) []string {
	raw := tokenPattern.FindAllString(query, -1)
	seen := make(map[string]struct{}, len(raw)*2)
	tokens := make([]string, 0, len(raw)*2)
	addToken := func(t string) {
		if utf8.RuneCountInString(t) < 2 {
			return
		}
		low := strings.ToLower(t)
		if _, ok := seen[low]; ok {
			return
		}
		seen[low] = struct{}{}
		tokens = append(tokens, low)
	}
	for _, t := range raw {
		addToken(t)
		if strings.Contains(t, "-") {
			for _, sub := range strings.Split(t, "-") {
				addToken(sub)
			}
		}
	}
	return tokens
}

// ---------------------------------------------------------------------------
// Layer 2: Tag matching
// ---------------------------------------------------------------------------

func layerTagMatch(tokens []string, index []SkillEntry) []int {
	scores := make([]int, len(index))
	for i, entry := range index {
		for _, tok := range tokens {
			for _, tag := range entry.Tags {
				if strings.Contains(strings.ToLower(tag), tok) {
					scores[i] += tagMatchScore
				}
			}
		}
	}
	return scores
}

// ---------------------------------------------------------------------------
// Layer 3: Name matching
// ---------------------------------------------------------------------------

func layerNameMatch(tokens []string, index []SkillEntry) []int {
	scores := make([]int, len(index))
	for i, entry := range index {
		nameLow := strings.ToLower(entry.Name)
		for _, tok := range tokens {
			if nameLow == tok {
				scores[i] += exactNameMatchScore
			} else if strings.Contains(nameLow, tok) {
				scores[i] += partialNameMatchScore
			}
		}
	}
	return scores
}

// ---------------------------------------------------------------------------
// Layer 4: Description matching
// ---------------------------------------------------------------------------

func layerDescriptionMatch(tokens []string, index []SkillEntry) []int {
	scores := make([]int, len(index))
	for i, entry := range index {
		descLow := strings.ToLower(entry.Description)
		for _, tok := range tokens {
			if strings.Contains(descLow, tok) {
				scores[i] += descriptionMatchScore
			}
		}
	}
	return scores
}

// ---------------------------------------------------------------------------
// Layer 5: Score aggregation
// ---------------------------------------------------------------------------

type scoredEntry struct {
	entry SkillEntry
	score int
}

func layerAggregate(index []SkillEntry, tagScores, nameScores, descScores []int) []scoredEntry {
	out := make([]scoredEntry, len(tagScores))
	for i := range tagScores {
		total := tagScores[i] + nameScores[i] + descScores[i]
		if tagScores[i] > 0 && nameScores[i] == 0 {
			total += tagOnlyBonus
		}
		out[i] = scoredEntry{entry: index[i], score: total}
	}
	return out
}

// ---------------------------------------------------------------------------
// Layer 6: Deduplication
// ---------------------------------------------------------------------------

func layerDedup(scored []scoredEntry) []scoredEntry {
	seen := make(map[string]int) // name -> index of best
	out := make([]scoredEntry, 0, len(scored))
	for _, s := range scored {
		if idx, ok := seen[s.entry.Name]; ok {
			if s.score > out[idx].score {
				out[idx] = s
			}
			continue
		}
		seen[s.entry.Name] = len(out)
		out = append(out, s)
	}
	return out
}

// ---------------------------------------------------------------------------
// Layer 7: Safety filter
// ---------------------------------------------------------------------------

func layerSafetyFilter(scored []scoredEntry) []scoredEntry {
	out := make([]scoredEntry, 0, len(scored))
	for _, s := range scored {
		if s.score <= 0 {
			continue
		}
		if s.entry.Name == "" {
			continue
		}
		if s.entry.Path == "" {
			continue
		}
		out = append(out, s)
	}
	return out
}
