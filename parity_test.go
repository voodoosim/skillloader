package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"testing"
)

type parityCatalogEntry struct {
	Name string   `json:"name"`
	Tags []string `json:"tags"`
}

type paritySearchResult struct {
	Score int      `json:"score"`
	Name  string   `json:"name"`
	Tags  []string `json:"tags"`
}

type parityQuery struct {
	ID      string               `json:"id"`
	Query   string               `json:"query"`
	Limit   int                  `json:"limit"`
	Results []paritySearchResult `json:"results"`
}

type parityQueries struct {
	SchemaVersion int                  `json:"schema_version"`
	Catalog       []parityCatalogEntry `json:"catalog"`
	Queries       []parityQuery        `json:"queries"`
}

type parityLoad struct {
	Name          string `json:"name"`
	ContentSHA256 string `json:"content_sha256"`
	Content       string `json:"content"`
}

type parityLoads struct {
	SchemaVersion int          `json:"schema_version"`
	Loads         []parityLoad `json:"loads"`
}

type paritySummary struct {
	CatalogTotal        int `json:"catalog_total"`
	CatalogMatches      int `json:"catalog_matches"`
	QueryTotal          int `json:"query_total"`
	TopOneMatches       int `json:"top_one_matches"`
	ExactRankingMatches int `json:"exact_ranking_matches"`
	LoadTotal           int `json:"load_total"`
	LoadMatches         int `json:"load_matches"`
}

func readParityJSON(t *testing.T, name string, target any) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("testdata", "parity", name))
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatal(err)
	}
}

func TestPythonParityFixtures(t *testing.T) {
	var queryFixtures parityQueries
	var loadFixtures parityLoads
	readParityJSON(t, "frozen_queries.json", &queryFixtures)
	readParityJSON(t, "frozen_loads.json", &loadFixtures)

	if queryFixtures.SchemaVersion != 1 || loadFixtures.SchemaVersion != 1 {
		t.Fatalf("unsupported parity fixture schema: queries=%d loads=%d", queryFixtures.SchemaVersion, loadFixtures.SchemaVersion)
	}
	if len(queryFixtures.Queries) != 10 || len(loadFixtures.Loads) != 10 {
		t.Fatalf("parity fixture size: queries=%d loads=%d, want 10 each", len(queryFixtures.Queries), len(loadFixtures.Loads))
	}

	root := filepath.Join("testdata", "parity", "home", ".codex", "skills")
	index, catalogErrors, err := BuildIndex([]string{root})
	if err != nil {
		t.Fatal(err)
	}
	if len(catalogErrors) != 0 {
		t.Fatalf("catalog errors: %v", catalogErrors)
	}

	gotCatalog := make([]parityCatalogEntry, 0, len(index))
	for _, entry := range index {
		tags := append([]string(nil), entry.Tags...)
		sort.Strings(tags)
		gotCatalog = append(gotCatalog, parityCatalogEntry{Name: entry.Name, Tags: tags})
	}
	if !reflect.DeepEqual(gotCatalog, queryFixtures.Catalog) {
		t.Fatalf("Go catalog differs from frozen Python catalog:\n got: %#v\nwant: %#v", gotCatalog, queryFixtures.Catalog)
	}

	engine := NewSearchEngine(index)
	topOneMatches := 0
	exactRankingMatches := 0
	for _, fixture := range queryFixtures.Queries {
		got := engine.Search(fixture.Query, fixture.Limit)
		gotResults := make([]parityCatalogEntry, 0, len(got))
		wantResults := make([]parityCatalogEntry, 0, len(fixture.Results))
		for _, result := range got {
			tags := append([]string(nil), result.Tags...)
			sort.Strings(tags)
			gotResults = append(gotResults, parityCatalogEntry{Name: result.Name, Tags: tags})
		}
		for _, result := range fixture.Results {
			wantResults = append(wantResults, parityCatalogEntry{Name: result.Name, Tags: result.Tags})
		}
		if len(gotResults) > 0 && len(wantResults) > 0 && gotResults[0].Name == wantResults[0].Name {
			topOneMatches++
		}
		if reflect.DeepEqual(gotResults, wantResults) {
			exactRankingMatches++
		}
	}

	loader := NewSkillLoader(index, []string{root}, NewCache())
	loadMatches := 0
	for _, fixture := range loadFixtures.Loads {
		fixture := fixture
		t.Run("load/"+fixture.Name, func(t *testing.T) {
			got, err := loader.Load(fixture.Name)
			if err != nil {
				t.Fatal(err)
			}
			if got.Name != fixture.Name || got.Content != fixture.Content || got.ContentSHA != fixture.ContentSHA256 {
				t.Fatalf("Go load differs from frozen Python load for %q", fixture.Name)
			}
			loadMatches++
		})
	}

	summary := paritySummary{
		CatalogTotal:        len(queryFixtures.Catalog),
		CatalogMatches:      len(gotCatalog),
		QueryTotal:          len(queryFixtures.Queries),
		TopOneMatches:       topOneMatches,
		ExactRankingMatches: exactRankingMatches,
		LoadTotal:           len(loadFixtures.Loads),
		LoadMatches:         loadMatches,
	}
	encoded, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("PARITY_SUMMARY=%s", encoded)
}
