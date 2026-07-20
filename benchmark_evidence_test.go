package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"
	"time"
)

type benchmarkEvidence struct {
	GoVersion  string                 `json:"go_version"`
	Catalog    int                    `json:"catalog_size"`
	Iterations int                    `json:"iterations"`
	Results    []benchmarkMeasurement `json:"results"`
}

type benchmarkMeasurement struct {
	Mode string        `json:"mode"`
	Op   string        `json:"operation"`
	P50  time.Duration `json:"p50_ns"`
	P95  time.Duration `json:"p95_ns"`
	Mean time.Duration `json:"mean_ns"`
}

func TestBenchmarkEvidence(t *testing.T) {
	if os.Getenv("SKILLLOADER_BENCHMARK") != "1" {
		t.Skip("set SKILLLOADER_BENCHMARK=1 to generate benchmark evidence")
	}

	const iterations = 50
	root := t.TempDir()
	const catalogSize = 100
	for i := 0; i < catalogSize; i++ {
		name := fmt.Sprintf("bench-skill-%03d", i)
		dir := filepath.Join(root, name)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
		content := fmt.Sprintf("---\nname: %s\ndescription: security review fixture %d\ntags: [benchmark, security, review]\n---\n# %s\n", name, i, name)
		if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	roots := []string{root}

	coldSearch := make([]time.Duration, 0, iterations)
	coldLoad := make([]time.Duration, 0, iterations)
	for i := 0; i < iterations; i++ {
		start := time.Now()
		index, errs, err := BuildIndex(roots)
		if err != nil || len(errs) != 0 {
			t.Fatalf("cold BuildIndex error=%v diagnostics=%v", err, errs)
		}
		NewSearchEngine(index).Search("security review", 5)
		coldSearch = append(coldSearch, time.Since(start))

		start = time.Now()
		loader := NewSkillLoader(index, roots, NewCache())
		if _, err := loader.Load("bench-skill-050"); err != nil {
			t.Fatal(err)
		}
		coldLoad = append(coldLoad, time.Since(start))
	}

	index, errs, err := BuildIndex(roots)
	if err != nil || len(errs) != 0 {
		t.Fatalf("warm setup error=%v diagnostics=%v", err, errs)
	}
	engine := NewSearchEngine(index)
	loader := NewSkillLoader(index, roots, NewCache())
	warmSearch := make([]time.Duration, 0, iterations)
	warmLoad := make([]time.Duration, 0, iterations)
	for i := 0; i < iterations; i++ {
		start := time.Now()
		engine.Search("security review", 5)
		warmSearch = append(warmSearch, time.Since(start))

		start = time.Now()
		if _, err := loader.Load("bench-skill-050"); err != nil {
			t.Fatal(err)
		}
		warmLoad = append(warmLoad, time.Since(start))
	}

	evidence := benchmarkEvidence{
		GoVersion:  runtime.Version(),
		Catalog:    catalogSize,
		Iterations: iterations,
		Results: []benchmarkMeasurement{
			measurement("cold", "search", coldSearch),
			measurement("cold", "load", coldLoad),
			measurement("warm", "search", warmSearch),
			measurement("warm", "load", warmLoad),
		},
	}
	data, err := json.MarshalIndent(evidence, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if output := os.Getenv("SKILLLOADER_BENCHMARK_OUTPUT"); output != "" {
		if err := os.WriteFile(output, append(data, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	fmt.Printf("BENCHMARK_EVIDENCE=%s\n", data)
}

func measurement(mode, op string, samples []time.Duration) benchmarkMeasurement {
	sorted := append([]time.Duration(nil), samples...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })
	var total time.Duration
	for _, sample := range samples {
		total += sample
	}
	return benchmarkMeasurement{
		Mode: mode,
		Op:   op,
		P50:  sorted[(len(sorted)-1)*50/100],
		P95:  sorted[(len(sorted)-1)*95/100],
		Mean: total / time.Duration(len(samples)),
	}
}
