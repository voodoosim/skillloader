package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// DoctorReport holds the result of a catalog diagnostic scan.
type DoctorReport struct {
	SkillCount int      `json:"skill_count"`
	ErrorCount int      `json:"error_count"`
	Errors     []string `json:"errors,omitempty"`
	CacheDocs  int      `json:"cache_docs"`
}

// Doctor scans the configured roots and reports catalog health.
func Doctor(roots []string, c *Cache) *DoctorReport {
	entries, errs, _ := BuildIndex(roots)
	report := &DoctorReport{
		SkillCount: len(entries),
		ErrorCount: len(errs),
		Errors:     errs,
		CacheDocs:  c.DocCount(),
	}

	seen := make(map[string]int)
	for _, e := range entries {
		seen[e.Name]++
	}
	for name, count := range seen {
		if count > 1 {
			report.ErrorCount++
			report.Errors = append(report.Errors,
				fmt.Sprintf("duplicate skill name: %s (%d occurrences)", name, count))
		}
	}

	for _, e := range entries {
		if len(e.Tags) == 0 {
			report.ErrorCount++
			report.Errors = append(report.Errors,
				fmt.Sprintf("missing tags: %s", e.Name))
		}
	}

	for _, root := range roots {
		info, err := os.Stat(root)
		if err != nil {
			report.ErrorCount++
			report.Errors = append(report.Errors,
				fmt.Sprintf("unreadable root: %s (%v)", root, err))
			continue
		}
		if !info.IsDir() {
			report.ErrorCount++
			report.Errors = append(report.Errors,
				fmt.Sprintf("root is not a directory: %s", root))
		}
	}

	return report
}

// DoctorJSON returns the doctor report as a JSON string.
func DoctorJSON(roots []string, c *Cache) string {
	report := Doctor(roots, c)
	out, _ := json.MarshalIndent(report, "", "  ")
	return string(out)
}

// ListJSON returns the full catalog index as JSON.
func ListJSON(roots []string) string {
	entries, _, _ := BuildIndex(roots)
	type listEntry struct {
		Name   string   `json:"name"`
		Tags   []string `json:"tags"`
		Source string   `json:"source"`
	}
	out := make([]listEntry, len(entries))
	for i, e := range entries {
		tags := e.Tags
		if tags == nil {
			tags = []string{}
		}
		out[i] = listEntry{
			Name:   e.Name,
			Tags:   tags,
			Source: e.Source,
		}
	}
	b, _ := json.MarshalIndent(out, "", "  ")
	return string(b)
}

// ListText returns a human-readable catalog listing.
func ListText(roots []string) string {
	entries, _, _ := BuildIndex(roots)
	var sb strings.Builder
	for _, e := range entries {
		tags := strings.Join(e.Tags, ", ")
		sb.WriteString(fmt.Sprintf("%-40s [%s]  %s\n", e.Name, e.Source, tags))
	}
	return sb.String()
}
