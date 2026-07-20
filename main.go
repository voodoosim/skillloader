package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	if len(os.Args) > 1 {
		runCLI(os.Args[1:])
		return
	}

	runServer()
}

func runServer() {
	roots := getRoots()

	cache := NewCache()
	index, errs, err := BuildIndex(roots)
	if err != nil {
		log.Fatalf("catalog build failed: %v", err)
	}
	if len(errs) > 0 {
		for _, e := range errs {
			log.Printf("catalog warning: %s", e)
		}
	}
	cache.StoreIndex(index)

	engine := NewSearchEngine(index)
	loader := NewSkillLoader(index, cache)

	server := mcp.NewServer(&mcp.Implementation{
		Name:    "skillloader",
		Version: "0.1.0",
	}, nil)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "search_skills",
		Description: "Search the skill catalog by task description. Returns bounded, ranked metadata matches. Use this before loading a skill to find the best match.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input SearchInput) (*mcp.CallToolResult, any, error) {
		if input.Query == "" {
			return nil, nil, fmt.Errorf("query is required")
		}
		limit := input.Limit
		if limit <= 0 || limit > 10 {
			limit = 5
		}

		results := engine.Search(input.Query, limit)

		output := map[string]interface{}{
			"query":   input.Query,
			"limit":   limit,
			"matches": results,
		}

		data, _ := json.MarshalIndent(output, "", "  ")
		return &mcp.CallToolResult{
			Content: []mcp.Content{
				&mcp.TextContent{Text: string(data)},
			},
		}, nil, nil
	})

	mcp.AddTool(server, &mcp.Tool{
		Name:        "load_skill",
		Description: "Load a skill by exact logical name. Returns the complete skill document. Use only the name returned by search_skills.",
	}, func(ctx context.Context, req *mcp.CallToolRequest, input LoadInput) (*mcp.CallToolResult, any, error) {
		if input.Name == "" {
			return nil, nil, fmt.Errorf("name is required")
		}

		result, err := loader.Load(input.Name)
		if err != nil {
			return nil, nil, fmt.Errorf("%v", err)
		}

		output := map[string]interface{}{
			"skill": result,
		}

		data, _ := json.MarshalIndent(output, "", "  ")
		return &mcp.CallToolResult{
			Content: []mcp.Content{
				&mcp.TextContent{Text: string(data)},
			},
		}, nil, nil
	})

	log.Printf("SkillLoader MCP server starting (roots: %d)", len(roots))
	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		log.Fatalf("server error: %v", err)
	}
}

func runCLI(args []string) {
	roots := getRoots()
	cache := NewCache()

	switch args[0] {
	case "list":
		if len(args) > 1 && args[1] == "--json" {
			fmt.Println(ListJSON(roots))
		} else {
			fmt.Print(ListText(roots))
		}

	case "doctor":
		if len(args) > 1 && args[1] == "--json" {
			fmt.Println(DoctorJSON(roots, cache))
		} else {
			report := Doctor(roots, cache)
			fmt.Printf("skills=%d errors=%d\n", report.SkillCount, report.ErrorCount)
			for _, e := range report.Errors {
				fmt.Println(e)
			}
		}

	default:
		fmt.Fprintf(os.Stderr, "usage: skillloader [list|doctor] [--json]\n")
		os.Exit(1)
	}
}

type SearchInput struct {
	Query string `json:"query" jsonschema:"required, the task description to search for matching skills"`
	Limit int    `json:"limit" jsonschema:"maximum results (1-10, default 5)"`
}

type LoadInput struct {
	Name string `json:"name" jsonschema:"required, the exact logical skill name from search results"`
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
		p = trimSpace(p)
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

func trimSpace(s string) string {
	start, end := 0, len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t') {
		end--
	}
	return s[start:end]
}
