package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestCLIHelpExitsSuccessfully(t *testing.T) {
	for _, args := range [][]string{{"--help"}, {"-h"}, {"help"}} {
		var stdout, stderr bytes.Buffer
		if code := runCLI(args, &stdout, &stderr); code != 0 {
			t.Fatalf("runCLI(%v) code = %d, want 0", args, code)
		}
		if !strings.Contains(stdout.String(), "usage: skillloader") {
			t.Fatalf("runCLI(%v) did not print usage", args)
		}
		if stderr.Len() != 0 {
			t.Fatalf("runCLI(%v) wrote stderr: %s", args, stderr.String())
		}
	}
}

func TestCLIUnknownCommandFails(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := runCLI([]string{"unknown"}, &stdout, &stderr); code != 1 {
		t.Fatalf("code = %d, want 1", code)
	}
	if !strings.Contains(stderr.String(), "unknown command") {
		t.Fatalf("stderr = %q", stderr.String())
	}
}
