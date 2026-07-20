package main

import (
	"encoding/gob"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func init() {
	gob.Register(SkillEntry{})
	gob.Register(catalogSnapshot{})
}

const cacheDirName = "skillloader"

type catalogSnapshot struct {
	Entries   []SkillEntry
	FileTimes map[string]time.Time
	BuiltAt   time.Time
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

func loadSnapshot() ([]SkillEntry, bool) {
	path, err := snapshotPath()
	if err != nil {
		return nil, false
	}

	f, err := os.Open(path)
	if err != nil {
		return nil, false
	}
	defer f.Close()

	var snap catalogSnapshot
	if err := gob.NewDecoder(f).Decode(&snap); err != nil {
		return nil, false
	}

	valid := true
	for _, entry := range snap.Entries {
		info, err := os.Stat(entry.Path)
		if err != nil {
			valid = false
			break
		}
		if stored, ok := snap.FileTimes[entry.Path]; !ok || !info.ModTime().Equal(stored) {
			valid = false
			break
		}
	}

	if !valid {
		return nil, false
	}

	return snap.Entries, true
}

func saveSnapshot(entries []SkillEntry) error {
	path, err := snapshotPath()
	if err != nil {
		return err
	}

	snap := catalogSnapshot{
		Entries:   entries,
		FileTimes: make(map[string]time.Time, len(entries)),
		BuiltAt:   time.Now(),
	}

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
