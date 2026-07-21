package main

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	if len(os.Args) > 1 {
		os.Exit(runCLI(os.Args[1:], os.Stdout, os.Stderr))
	}

	if err := runServer(); err != nil {
		log.Fatal(err)
	}
}

func runServer() error {
	roots := getRoots()

	cache := NewCache()
	index, errs := tryLoadIndex(roots)
	if len(errs) > 0 {
		for _, e := range errs {
			log.Printf("catalog warning: %s", e)
		}
	}
	cache.StoreIndex(index)

	server := newServer(index, roots, cache)
	log.Printf("SkillLoader MCP server starting (roots: %d, skills: %d)", len(roots), len(index))
	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		return fmt.Errorf("server stopped: %w", err)
	}
	return nil
}

type SearchOutput struct {
	Query           string        `json:"query,omitempty"`
	Limit           int           `json:"limit,omitempty"`
	Matches         []SearchMatch `json:"matches,omitempty"`
	CatalogRevision string        `json:"catalog_revision"`
	QueryHash       string        `json:"query_hash"`
	Cached          bool          `json:"cached"`
	Error           *SkillError   `json:"error,omitempty"`
}

type LoadOutput struct {
	Skill           *LoadResult `json:"skill,omitempty"`
	CatalogRevision string      `json:"catalog_revision"`
	ContentSHA256   string      `json:"content_sha256,omitempty"`
	Cached          bool        `json:"cached"`
	Error           *SkillError `json:"error,omitempty"`
}

const (
	maxSearchQueryRunes = 4096
	maxSkillNameRunes   = 256
)

func newServer(index []SkillEntry, roots []string, cache *Cache) *mcp.Server {
	engine := NewSearchEngine(index)
	loader := NewSkillLoader(index, roots, cache)

	server := mcp.NewServer(&mcp.Implementation{
		Name:    "skillloader",
		Version: "0.1.0",
	}, nil)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "search_skills",
		Description: "Search the skill catalog by task description. Returns bounded, ranked metadata matches. Use this before loading a skill to find the best match.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input SearchInput) (*mcp.CallToolResult, SearchOutput, error) {
		query := strings.TrimSpace(input.Query)
		if query == "" || utf8.RuneCountInString(query) > maxSearchQueryRunes {
			return &mcp.CallToolResult{IsError: true}, SearchOutput{
				Matches:         []SearchMatch{},
				CatalogRevision: cache.IndexHash(),
				Error:           skillError("INVALID_ARGUMENT", "A non-empty search query is required."),
			}, nil
		}
		limit := 5
		if input.Limit != nil {
			limit = *input.Limit
			if limit <= 0 || limit > 10 {
				limit = 5
			}
		}

		catalogRevision := cache.IndexHash()
		queryHash := searchQueryHash(query, limit, catalogRevision)
		if input.KnownQueryHash == queryHash {
			return nil, SearchOutput{
				Query:           query,
				Limit:           limit,
				CatalogRevision: catalogRevision,
				QueryHash:       queryHash,
				Cached:          true,
			}, nil
		}
		results := engine.Search(query, limit)

		return nil, SearchOutput{
			Query:           query,
			Limit:           limit,
			Matches:         results,
			CatalogRevision: catalogRevision,
			QueryHash:       queryHash,
		}, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "load_skill",
		Description: "Load a skill by exact logical name. Returns the complete skill document. Use only the name returned by search_skills.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input LoadInput) (*mcp.CallToolResult, LoadOutput, error) {
		name := strings.TrimSpace(input.Name)
		if name == "" || utf8.RuneCountInString(name) > maxSkillNameRunes {
			return &mcp.CallToolResult{IsError: true}, LoadOutput{
				CatalogRevision: cache.IndexHash(),
				Error:           skillError("INVALID_ARGUMENT", "A non-empty logical skill name is required."),
			}, nil
		}

		result, err := loader.Load(name)
		if err != nil {
			var appErr *SkillError
			if !errors.As(err, &appErr) {
				appErr = skillError("INTERNAL_ERROR", "The skill could not be loaded.")
			}
			return &mcp.CallToolResult{IsError: true}, LoadOutput{
				CatalogRevision: cache.IndexHash(),
				Error:           appErr,
			}, nil
		}

		catalogRevision := cache.IndexHash()
		if input.KnownContentSHA256 == result.ContentSHA {
			return nil, LoadOutput{
				CatalogRevision: catalogRevision,
				ContentSHA256:   result.ContentSHA,
				Cached:          true,
			}, nil
		}
		return nil, LoadOutput{
			Skill:           result,
			CatalogRevision: catalogRevision,
			ContentSHA256:   result.ContentSHA,
		}, nil
	})

	return server
}

func runCLI(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 || args[0] == "help" || args[0] == "--help" || args[0] == "-h" {
		printUsage(stdout)
		return 0
	}

	roots := getRoots()
	cache := NewCache()

	switch args[0] {
	case "list":
		if len(args) > 1 && args[1] == "--json" {
			fmt.Fprintln(stdout, ListJSON(roots))
		} else {
			fmt.Fprint(stdout, ListText(roots))
		}

	case "doctor":
		if len(args) > 1 && args[1] == "--json" {
			fmt.Fprintln(stdout, DoctorJSON(roots, cache))
		} else {
			report := Doctor(roots, cache)
			fmt.Fprintf(stdout, "skills=%d errors=%d warnings=%d\n", report.SkillCount, report.ErrorCount, report.WarningCount)
			for _, e := range report.Errors {
				fmt.Fprintln(stdout, e)
			}
			for _, warning := range report.Warnings {
				fmt.Fprintln(stdout, warning)
			}
		}

	default:
		fmt.Fprintf(stderr, "unknown command: %s\n", args[0])
		printUsage(stderr)
		return 1
	}
	return 0
}

func printUsage(w io.Writer) {
	fmt.Fprintln(w, "usage: skillloader [list|doctor] [--json]")
	fmt.Fprintln(w, "       skillloader [help|--help|-h]")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "list    list catalog metadata")
	fmt.Fprintln(w, "doctor  diagnose roots, documents, duplicates, and missing tags")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "SKILLLOADER_ROOTS is a comma-separated path list; no quote, tilde, or glob expansion.")
}

type SearchInput struct {
	Query          string `json:"query" jsonschema:"required, the task description to search for matching skills"`
	Limit          *int   `json:"limit,omitempty" jsonschema:"maximum results (1-10, default 5)"`
	KnownQueryHash string `json:"known_query_hash,omitempty" jsonschema:"hash returned by a previous identical search"`
}

type LoadInput struct {
	Name               string `json:"name" jsonschema:"required, the exact logical skill name from search results"`
	KnownContentSHA256 string `json:"known_content_sha256,omitempty" jsonschema:"content hash returned by a previous load"`
}

func searchQueryHash(query string, limit int, catalogRevision string) string {
	value := fmt.Sprintf("%s\x00%d\x00%s", query, limit, catalogRevision)
	return fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(value)))
}

func getRoots() []string {
	if env := os.Getenv("SKILLLOADER_ROOTS"); env != "" {
		return splitCSV(env)
	}
	return DefaultRoots()
}

func splitCSV(s string) []string {
	var parts []string
	for _, p := range splitSimple(s, ',') {
		p = strings.TrimSpace(p)
		if p != "" {
			parts = append(parts, p)
		}
	}
	return parts
}

func splitSimple(s string, sep rune) []string {
	var parts []string
	start := 0
	for i, r := range s {
		if r == sep {
			parts = append(parts, s[start:i])
			start = i + 1
		}
	}
	parts = append(parts, s[start:])
	return parts
}
