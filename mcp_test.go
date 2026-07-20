package main

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestMCPToolsExposeStructuredResultsAndRedactedErrors(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "mcp-test")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	content := "---\nname: mcp-test\ndescription: MCP integration fixture\ntags: [mcp, test]\n---\n# MCP Test\n"
	if err := os.WriteFile(filepath.Join(dir, "SKILL.md"), []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	index, buildErrs, err := BuildIndex([]string{root})
	if err != nil || len(buildErrs) != 0 {
		t.Fatalf("BuildIndex error=%v diagnostics=%v", err, buildErrs)
	}
	cache := NewCache()
	cache.StoreIndex(index)

	ctx := context.Background()
	clientTransport, serverTransport := mcp.NewInMemoryTransports()
	serverSession, err := newServer(index, []string{root}, cache).Connect(ctx, serverTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer serverSession.Close()
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "0.0.1"}, nil)
	clientSession, err := client.Connect(ctx, clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer clientSession.Close()

	listed, err := clientSession.ListTools(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, tool := range listed.Tools {
		names = append(names, tool.Name)
		if tool.OutputSchema == nil {
			t.Fatalf("tool %s has no output schema", tool.Name)
		}
	}
	sort.Strings(names)
	if strings.Join(names, ",") != "load_skill,search_skills" {
		t.Fatalf("tools = %v", names)
	}

	searchResult, err := clientSession.CallTool(ctx, &mcp.CallToolParams{
		Name:      "search_skills",
		Arguments: map[string]any{"query": "MCP integration", "limit": 3},
	})
	if err != nil {
		t.Fatal(err)
	}
	if searchResult.IsError || searchResult.StructuredContent == nil {
		t.Fatalf("search result = %#v", searchResult)
	}
	var searchOutput SearchOutput
	decodeStructured(t, searchResult.StructuredContent, &searchOutput)
	if searchOutput.CatalogRevision == "" || len(searchOutput.Matches) != 1 || searchOutput.Matches[0].Name != "mcp-test" {
		t.Fatalf("search output = %#v", searchOutput)
	}
	if len(searchResult.Content) != 1 {
		t.Fatalf("search text compatibility content = %#v", searchResult.Content)
	}

	searchWithoutLimit, err := clientSession.CallTool(ctx, &mcp.CallToolParams{
		Name:      "search_skills",
		Arguments: map[string]any{"query": "MCP integration"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if searchWithoutLimit.IsError {
		t.Fatalf("search without limit should succeed, got: %#v", searchWithoutLimit)
	}
	var searchNoLimitOutput SearchOutput
	decodeStructured(t, searchWithoutLimit.StructuredContent, &searchNoLimitOutput)
	if searchNoLimitOutput.Limit != 5 {
		t.Fatalf("default limit = %d, want 5", searchNoLimitOutput.Limit)
	}

	loadSuccess, err := clientSession.CallTool(ctx, &mcp.CallToolParams{
		Name:      "load_skill",
		Arguments: map[string]any{"name": "mcp-test"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if loadSuccess.IsError || loadSuccess.StructuredContent == nil {
		t.Fatalf("load success result = %#v", loadSuccess)
	}
	var loadSuccessOutput LoadOutput
	decodeStructured(t, loadSuccess.StructuredContent, &loadSuccessOutput)
	if loadSuccessOutput.CatalogRevision == "" || loadSuccessOutput.Skill == nil || loadSuccessOutput.Skill.Name != "mcp-test" {
		t.Fatalf("load success output = %#v", loadSuccessOutput)
	}

	loadResult, err := clientSession.CallTool(ctx, &mcp.CallToolParams{
		Name:      "load_skill",
		Arguments: map[string]any{"name": "missing"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !loadResult.IsError || loadResult.StructuredContent == nil {
		t.Fatalf("load error result = %#v", loadResult)
	}
	var loadOutput LoadOutput
	decodeStructured(t, loadResult.StructuredContent, &loadOutput)
	if loadOutput.Error == nil || loadOutput.Error.Code != "SKILL_NOT_FOUND" {
		t.Fatalf("load output = %#v", loadOutput)
	}
	encoded, err := json.Marshal(loadResult)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), root) {
		t.Fatalf("MCP error leaked trusted root: %s", encoded)
	}
}

func decodeStructured(t *testing.T, value any, target any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatal(err)
	}
}
