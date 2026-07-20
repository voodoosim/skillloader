package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func makeIntegrationSkills(root string) ([]string, error) {
	skills := map[string]struct {
		name, desc, tags, body string
	}{
		"code-review": {
			"code-review",
			"Review Go code for security and style issues across packages",
			"code, review, security, go",
			"# Code Review Skill\n\nAnalyze source code for common Go mistakes.\n\nChecks:\n- SQL injection\n- unchecked errors\n- race conditions\n",
		},
		"deploy-script": {
			"deploy-script",
			"Generate deploy scripts with fleet rollout and rollback steps",
			"deploy, rollout, rollback, fleet",
			"# Deploy Script Generator\n\nProduces an idempotent deploy script.\n\nStages:\n1. drain old\n2. push artifact\n3. warm\n4. swap\n",
		},
		"korean-help": {
			"korean-help",
			"사용자 질문에 한국어로 응답하는 헬프데스크 스킬",
			"한글, 도움말, faq",
			"# 한국어 헬프데스크\n\n빈출 질문:\n- 서버 접속 불가\n- 배포 롤백\n- 로그 확인\n\n모든 응답은 한국어로 제공한다.\n",
		},
		"data-migrate": {
			"data-migrate",
			"Plan and execute database schema migrations with zero-downtime",
			"database, migration, sql, zero-downtime",
			"# Database Migration\n\nStrategy: expand-contract.\n\n1. add new column (nullable)\n2. backfill in batches\n3. switch application\n4. drop old column\n",
		},
		"log-inspect": {
			"log-inspect",
			"Inspect structured logs with jq patterns and anomaly detection hints",
			"logs, jq, anomaly, debug",
			"# Log Inspector\n\nCommon jq patterns:\n- `jq '.level'`\n- `jq 'select(.status >= 500)'`\n- `jq 'group_by(.path)'`\n",
		},
	}

	var paths []string
	for key, s := range skills {
		dir := filepath.Join(root, key)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, err
		}
		fm := fmt.Sprintf("---\nname: %s\ndescription: \"%s\"\ntags: [%s]\n---\n%s", s.name, s.desc, s.tags, s.body)
		p := filepath.Join(dir, "SKILL.md")
		if err := os.WriteFile(p, []byte(fm), 0o644); err != nil {
			return nil, err
		}
		paths = append(paths, p)
	}
	return paths, nil
}

func newIntegrationClient(t *testing.T, root string) (*mcp.ClientSession, context.CancelFunc) {
	t.Helper()
	index, buildErrs, err := BuildIndex([]string{root})
	if err != nil || len(buildErrs) != 0 {
		t.Fatalf("BuildIndex error=%v diagnostics=%v", err, buildErrs)
	}
	cache := NewCache()
	cache.StoreIndex(index)

	ctx, cancel := context.WithCancel(context.Background())
	clientTransport, serverTransport := mcp.NewInMemoryTransports()
	serverSession, err := newServer(index, []string{root}, cache).Connect(ctx, serverTransport, nil)
	if err != nil {
		cancel()
		t.Fatal(err)
	}
	t.Cleanup(func() {
		serverSession.Close()
		cancel()
	})

	client := mcp.NewClient(&mcp.Implementation{Name: "integration-client", Version: "0.1.0"}, nil)
	clientSession, err := client.Connect(ctx, clientTransport, nil)
	if err != nil {
		cancel()
		t.Fatal(err)
	}
	return clientSession, cancel
}

func TestCodexPatternSearchLoadVerify(t *testing.T) {
	root := t.TempDir()
	_, err := makeIntegrationSkills(root)
	if err != nil {
		t.Fatal(err)
	}

	client, cancel := newIntegrationClient(t, root)
	defer cancel()
	ctx := context.Background()

	scenarios := []struct {
		label, query    string
		wantTop         string
		wantContentLine string
	}{
		{"korean query", "한국어 도움말", "korean-help", "모든 응답은 한국어로 제공한다."},
		{"english code review", "security review go code", "code-review", "SQL injection"},
		{"deploy with rollback", "fleet deploy rollout rollback", "deploy-script", "idempotent deploy script"},
		{"database schema", "database migration zero downtime sql", "data-migrate", "expand-contract"},
		{"log inspection", "jq structured logs anomaly", "log-inspect", "jq '.level'"},
	}

	for _, sc := range scenarios {
		t.Run(sc.label, func(t *testing.T) {
			// Phase 1: search
			searchResult, err := client.CallTool(ctx, &mcp.CallToolParams{
				Name:      "search_skills",
				Arguments: map[string]any{"query": sc.query, "limit": 3},
			})
			if err != nil {
				t.Fatal(err)
			}
			if searchResult.IsError {
				t.Fatalf("search error: %#v", searchResult)
			}
			var searchOutput SearchOutput
			decodeStructured(t, searchResult.StructuredContent, &searchOutput)
			if len(searchOutput.Matches) == 0 {
				t.Fatalf("no search results for %q", sc.query)
			}
			if searchOutput.Matches[0].Name != sc.wantTop {
				t.Fatalf("top-1 for %q: got %q, want %q", sc.query, searchOutput.Matches[0].Name, sc.wantTop)
			}

			// Phase 2: load the top result
			loadResult, err := client.CallTool(ctx, &mcp.CallToolParams{
				Name:      "load_skill",
				Arguments: map[string]any{"name": sc.wantTop},
			})
			if err != nil {
				t.Fatal(err)
			}
			if loadResult.IsError {
				t.Fatalf("load error: %#v", loadResult)
			}
			var loadOutput LoadOutput
			decodeStructured(t, loadResult.StructuredContent, &loadOutput)
			if loadOutput.Skill == nil {
				t.Fatal("load returned nil skill")
			}

			// Phase 3: verify complete document
			if loadOutput.Skill.Name != sc.wantTop {
				t.Fatalf("loaded name = %q, want %q", loadOutput.Skill.Name, sc.wantTop)
			}
			if !strings.Contains(loadOutput.Skill.Content, sc.wantContentLine) {
				t.Fatalf("loaded content missing %q in\n%s", sc.wantContentLine, loadOutput.Skill.Content)
			}
			if loadOutput.Skill.ContentSHA == "" {
				t.Fatal("loaded content has no SHA256")
			}
			if loadOutput.CatalogRevision == "" {
				t.Fatal("loaded result has no catalog revision")
			}
		})
	}
}

func TestCodexPatternSearchLoadConsistency(t *testing.T) {
	root := t.TempDir()
	_, err := makeIntegrationSkills(root)
	if err != nil {
		t.Fatal(err)
	}

	client, cancel := newIntegrationClient(t, root)
	defer cancel()
	ctx := context.Background()

	searchResult, err := client.CallTool(ctx, &mcp.CallToolParams{
		Name:      "search_skills",
		Arguments: map[string]any{"query": "code deploy log", "limit": 10},
	})
	if err != nil {
		t.Fatal(err)
	}
	var searchOutput SearchOutput
	decodeStructured(t, searchResult.StructuredContent, &searchOutput)
	if len(searchOutput.Matches) < 2 {
		t.Fatalf("expected at least 2 search results, got %d", len(searchOutput.Matches))
	}

	for i, match := range searchOutput.Matches {
		t.Run(fmt.Sprintf("load_search_match_%d_%s", i, match.Name), func(t *testing.T) {
			loadResult, err := client.CallTool(ctx, &mcp.CallToolParams{
				Name:      "load_skill",
				Arguments: map[string]any{"name": match.Name},
			})
			if err != nil {
				t.Fatal(err)
			}
			if loadResult.IsError {
				t.Fatalf("load error for %s: %#v", match.Name, loadResult)
			}
			var loadOutput LoadOutput
			decodeStructured(t, loadResult.StructuredContent, &loadOutput)
			if loadOutput.Skill == nil || loadOutput.Skill.Name != match.Name {
				t.Fatalf("search/load name mismatch: search=%s load=%v", match.Name, loadOutput.Skill)
			}
		})
	}
}

func TestCodexPatternErrorPropagation(t *testing.T) {
	root := t.TempDir()
	_, err := makeIntegrationSkills(root)
	if err != nil {
		t.Fatal(err)
	}

	client, cancel := newIntegrationClient(t, root)
	defer cancel()
	ctx := context.Background()

	loadResult, err := client.CallTool(ctx, &mcp.CallToolParams{
		Name:      "load_skill",
		Arguments: map[string]any{"name": "nonexistent-xyz"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !loadResult.IsError {
		t.Fatal("expected error for missing skill")
	}
	var loadOutput LoadOutput
	decodeStructured(t, loadResult.StructuredContent, &loadOutput)
	if loadOutput.Error == nil || loadOutput.Error.Code != "SKILL_NOT_FOUND" {
		t.Fatalf("expected SKILL_NOT_FOUND error, got %#v", loadOutput.Error)
	}
	if loadOutput.Skill != nil {
		t.Fatal("error result should have nil skill")
	}

	encoded, err := json.Marshal(loadResult)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), root) {
		t.Fatalf("error leaked trusted root: %s", encoded)
	}
}

func TestCodexPatternSearchResultVariants(t *testing.T) {
	root := t.TempDir()
	_, err := makeIntegrationSkills(root)
	if err != nil {
		t.Fatal(err)
	}

	client, cancel := newIntegrationClient(t, root)
	defer cancel()
	ctx := context.Background()

	cases := []struct {
		label    string
		args     map[string]any
		wantMin  int
		wantMax  int
		wantName string
	}{
		{"limit 1", map[string]any{"query": "python", "limit": 1}, 0, 1, ""},
		{"no limit", map[string]any{"query": "deploy"}, 1, 5, "deploy-script"},
		{"limit 10", map[string]any{"query": "code", "limit": 10}, 1, 5, "code-review"},
		{"korean only", map[string]any{"query": "한글", "limit": 5}, 1, 5, "korean-help"},
	}

	for _, tc := range cases {
		t.Run(tc.label, func(t *testing.T) {
			result, err := client.CallTool(ctx, &mcp.CallToolParams{
				Name:      "search_skills",
				Arguments: tc.args,
			})
			if err != nil {
				t.Fatal(err)
			}
			if result.IsError {
				t.Fatalf("search error: %#v", result)
			}
			var output SearchOutput
			decodeStructured(t, result.StructuredContent, &output)
			if len(output.Matches) < tc.wantMin || len(output.Matches) > tc.wantMax {
				t.Fatalf("%s: got %d matches, want [%d,%d]", tc.label, len(output.Matches), tc.wantMin, tc.wantMax)
			}
			if tc.wantName != "" && output.Matches[0].Name != tc.wantName {
				t.Fatalf("%s: top-1 = %q, want %q", tc.label, output.Matches[0].Name, tc.wantName)
			}
		})
	}
}
