package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDoctorTreatsMissingTagsAsWarning(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "tagless")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("---\nname: tagless\ndescription: no tags\n---\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	report := Doctor([]string{root}, NewCache())
	if report.ErrorCount != 0 || report.WarningCount != 1 {
		t.Fatalf("errors=%d warnings=%d, want 0/1: %#v", report.ErrorCount, report.WarningCount, report)
	}
}

func TestDoctorRedactsRootPath(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "private-root")
	output := DoctorJSON([]string{missing}, NewCache())
	if strings.Contains(output, missing) {
		t.Fatalf("doctor output leaked configured root: %s", output)
	}
	if !strings.Contains(output, "root[0]") {
		t.Fatalf("doctor output lacks redacted root identifier: %s", output)
	}
}

func TestBuildIndexRedactsInvalidDocumentPath(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "private-skill")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "SKILL.md")
	if err := os.WriteFile(path, []byte("# no frontmatter\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	_, errs, err := BuildIndex([]string{root})
	if err != nil {
		t.Fatal(err)
	}
	if len(errs) != 1 {
		t.Fatalf("errors = %#v, want one", errs)
	}
	if strings.Contains(errs[0], root) || strings.Contains(errs[0], "private-skill") {
		t.Fatalf("catalog error leaked path: %q", errs[0])
	}
}

func TestDoctorDetectsDuplicateAndInvalidRoot(t *testing.T) {
	root := t.TempDir()
	for i := 0; i < 2; i++ {
		dir := filepath.Join(root, "skill", string(rune('a'+i)))
		if err := os.MkdirAll(dir, 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("---\nname: duplicate\ndescription: x\n---\n"), 0644); err != nil {
			t.Fatal(err)
		}
	}
	report := Doctor([]string{root, filepath.Join(root, "skill", "a", "SKILL.md")}, NewCache())
	if report.ErrorCount < 2 {
		t.Fatalf("expected duplicate and non-directory errors: %+v", report)
	}
}

func TestListOutputsAreValid(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "skill")
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte("---\nname: listed\ndescription: x\ntags: [x]\n---\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(ListText([]string{root}), "listed") || !strings.Contains(ListJSON([]string{root}), "listed") {
		t.Fatal("list output missing skill")
	}
}
