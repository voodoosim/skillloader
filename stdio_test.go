package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestStdioMCPProcessRoundTrip(t *testing.T) {
	root := t.TempDir()
	cache := t.TempDir()
	skillDir := filepath.Join(root, "stdio-fixture")
	if err := os.MkdirAll(skillDir, 0o755); err != nil {
		t.Fatal(err)
	}
	content := "---\nname: stdio-fixture\ndescription: process transport fixture\ntags: [stdio, test]\n---\n# Stdio Fixture\n"
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	binary := filepath.Join(t.TempDir(), "skillloader")
	build := exec.Command("go", "build", "-o", binary, ".")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, output)
	}

	cmd := exec.Command(binary)
	cmd.Env = append(os.Environ(),
		"SKILLLOADER_ROOTS="+root,
		"XDG_CACHE_HOME="+cache,
	)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client := mcp.NewClient(&mcp.Implementation{Name: "stdio-test-client", Version: "0.0.1"}, nil)
	session, err := client.Connect(ctx, &mcp.CommandTransport{Command: cmd}, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()

	tools, err := session.ListTools(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(tools.Tools) != 2 {
		t.Fatalf("stdio tools = %d, want 2", len(tools.Tools))
	}

	search, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      "search_skills",
		Arguments: map[string]any{"query": "process transport"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if search.IsError || search.StructuredContent == nil {
		t.Fatalf("stdio search = %#v", search)
	}
	var searchOutput SearchOutput
	decodeStructured(t, search.StructuredContent, &searchOutput)
	if len(searchOutput.Matches) != 1 || searchOutput.Matches[0].Name != "stdio-fixture" {
		t.Fatalf("stdio search output = %#v", searchOutput)
	}

	load, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      "load_skill",
		Arguments: map[string]any{"name": "stdio-fixture"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if load.IsError || load.StructuredContent == nil {
		t.Fatalf("stdio load = %#v", load)
	}
	var loadOutput LoadOutput
	decodeStructured(t, load.StructuredContent, &loadOutput)
	if loadOutput.Skill == nil || loadOutput.Skill.Content != content {
		t.Fatalf("stdio load output = %#v", loadOutput)
	}
}
