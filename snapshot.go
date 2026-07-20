package main

import (
	"crypto/sha256"
	"encoding/gob"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

func init() {
	gob.Register(SkillEntry{})
	gob.Register(catalogSnapshot{})
}

const cacheDirName = "skillloader"

type catalogSnapshot struct {
	Entries         []SkillEntry
	FileTimes       map[string]time.Time
	NormalizedRoots []string
	RootsHash       string
	DirFingerprint  string
	Errors          []string
	BuiltAt         time.Time
}

func snapshotPath() (string, error) {
	cache, err := os.UserCacheDir()
	if err != nil {
		return "", err
	}
	dir := filepath.Join(cache, cacheDirName)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return "", err
	}
	return filepath.Join(dir, "catalog.gob"), nil
}

func loadSnapshot(roots []string) ([]SkillEntry, []string, bool) {
	path, err := snapshotPath()
	if err != nil {
		return nil, nil, false
	}

	f, err := os.Open(path)
	if err != nil {
		return nil, nil, false
	}
	defer f.Close()

	var snap catalogSnapshot
	if err := gob.NewDecoder(f).Decode(&snap); err != nil {
		return nil, nil, false
	}

	r := normalizeRoots(roots)
	if snap.RootsHash != hashRoots(r) {
		return nil, nil, false
	}

	for _, entry := range snap.Entries {
		if !entryWithinRoots(r, entry.Path) {
			return nil, nil, false
		}
	}

	currentFP, err := dirFingerprint(roots)
	if err != nil || currentFP != snap.DirFingerprint {
		return nil, nil, false
	}

	for _, entry := range snap.Entries {
		info, err := os.Stat(entry.Path)
		if err != nil {
			return nil, nil, false
		}
		stored, ok := snap.FileTimes[entry.Path]
		if !ok || !info.ModTime().Equal(stored) {
			return nil, nil, false
		}
		if fileChecksum(entry.Path) != entry.Checksum {
			return nil, nil, false
		}
	}

	out := copyEntries(snap.Entries)
	outErrs := make([]string, len(snap.Errors))
	copy(outErrs, snap.Errors)
	return out, outErrs, true
}

func saveSnapshot(entries []SkillEntry, errs []string, roots []string) error {
	path, err := snapshotPath()
	if err != nil {
		return err
	}

	r := normalizeRoots(roots)
	fp, err := dirFingerprint(roots)
	if err != nil {
		return err
	}

	snap := catalogSnapshot{
		Entries:         copyEntries(entries),
		FileTimes:       make(map[string]time.Time, len(entries)),
		NormalizedRoots: r,
		RootsHash:       hashRoots(r),
		DirFingerprint:  fp,
		Errors:          make([]string, len(errs)),
		BuiltAt:         time.Now(),
	}
	copy(snap.Errors, errs)

	for _, entry := range entries {
		info, err := os.Stat(entry.Path)
		if err != nil {
			continue
		}
		snap.FileTimes[entry.Path] = info.ModTime()
	}

	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	if err := gob.NewEncoder(f).Encode(snap); err != nil {
		return fmt.Errorf("encode snapshot: %w", err)
	}

	return nil
}

func clearSnapshot() error {
	path, err := snapshotPath()
	if err != nil {
		return err
	}
	return os.Remove(path)
}

func normalizeRoots(roots []string) []string {
	out := make([]string, len(roots))
	for i, r := range roots {
		abs, _ := filepath.Abs(r)
		resolved, _ := filepath.EvalSymlinks(abs)
		out[i] = resolved
	}
	sort.Strings(out)
	return out
}

func hashRoots(roots []string) string {
	h := sha256.New()
	h.Write([]byte(strings.Join(roots, "\n")))
	return fmt.Sprintf("%x", h.Sum(nil))
}

func dirFingerprint(roots []string) (string, error) {
	paths, err := DiscoverSkills(roots)
	if err != nil {
		return "", err
	}
	h := sha256.New()
	for _, p := range paths {
		h.Write([]byte(p))
		h.Write([]byte{0})
	}
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

func entryWithinRoots(normalizedRoots []string, path string) bool {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return false
	}
	resolvedPath, err := filepath.EvalSymlinks(absPath)
	if err != nil {
		return false
	}
	for _, root := range normalizedRoots {
		rel, err := filepath.Rel(root, resolvedPath)
		if err == nil && rel != "." && !filepath.IsAbs(rel) && !strings.HasPrefix(rel, "..") {
			return true
		}
	}
	return false
}

func copyEntries(src []SkillEntry) []SkillEntry {
	out := make([]SkillEntry, len(src))
	copy(out, src)
	return out
}

func fileChecksum(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	h := sha256.Sum256(data)
	return fmt.Sprintf("%x", h[:])
}
