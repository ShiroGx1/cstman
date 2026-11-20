// Command cstman-mcp is the CSTMAN MCP server over stdio. An MCP host (Claude
// Code, Cursor, …) spawns it and speaks JSON-RPC on stdin/stdout; the three
// cstman_* tools wrap the CSTMAN Engine. Logs go to stderr only — stdout
// is the protocol channel.
//
// By default it opens the SHARED file recovery store (CSTMAN_CCR_DB, else
// ~/.cstman/ccr.db) — the same store the CSTMAN gateway writes — so a
// cstman_retrieve here resolves handles the proxy disclosed (this is what lets a
// wrapped agent recover proxy-elided detail on streaming requests). Set
// CSTMAN_MCP_EPHEMERAL=1 for a fresh in-memory store that touches no disk.
package main

import _ "github.com/JuliusBrussee/cstman/shared/platform/envcompat"

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"

	"github.com/JuliusBrussee/cstman/engine"
	"github.com/JuliusBrussee/cstman/engine/ccr"
	"github.com/JuliusBrussee/cstman/mcp"
)

var version = "dev"

func main() {
	if handled, code := handleArgs(os.Args[1:], os.Stdout, os.Stderr); handled {
		os.Exit(code)
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))

	store, err := openRecoveryStore()
	if err != nil {
		logger.Error("open recovery store", "err", err)
		os.Exit(1)
	}
	defer store.Close()

	eng := engine.New(store, nil)
	srv := mcp.NewServerVersion("cstman", version, mcp.EngineTools(eng, logger), logger)
	if err := srv.Serve(os.Stdin, os.Stdout); err != nil {
		logger.Error("serve", "err", err)
		os.Exit(1)
	}
}

func handleArgs(args []string, stdout, stderr io.Writer) (bool, int) {
	if len(args) == 0 {
		return false, 0
	}
	if len(args) == 2 && args[0] == "version" && args[1] == "--json" {
		err := json.NewEncoder(stdout).Encode(map[string]any{
			"version":      version,
			"schema":       "cstman.mcp.version.v1",
			"capabilities": []string{"mcp_recovery", "build_stamped_version", "recovery_verification"},
		})
		if err != nil {
			return true, 1
		}
		return true, 0
	}
	_, _ = io.WriteString(stderr, "usage: cstman-mcp [version --json]\n")
	return true, 2
}

// openRecoveryStore opens the shared file CCR store the proxy uses, so handles are
// resolvable across processes. CSTMAN_MCP_EPHEMERAL=1 forces an in-memory store
// (no disk). The path mirrors the proxy: CSTMAN_CCR_DB, else ~/.cstman/ccr.db.
func openRecoveryStore() (*ccr.Store, error) {
	if os.Getenv("CSTMAN_MCP_EPHEMERAL") == "1" {
		return ccr.OpenMemory()
	}
	path := os.Getenv("CSTMAN_CCR_DB")
	if path == "" {
		home := os.Getenv("CSTMAN_HOME")
		if home == "" {
			h, err := os.UserHomeDir()
			if err != nil {
				return ccr.OpenMemory()
			}
			home = filepath.Join(h, ".cstman")
		}
		if err := os.MkdirAll(home, 0o700); err != nil {
			return nil, fmt.Errorf("create recovery directory %q: %w", home, err)
		}
		path = filepath.Join(home, "ccr.db")
	}
	return ccr.Open(path)
}
