package envcompat

import (
	"os"
	"path/filepath"
	"strings"
)

// Apply keeps pre-rebrand environment variables usable while CSTMAN_* names
// become the public form. An explicitly set CSTMAN_* value always wins.
func Apply() {
	for _, pair := range os.Environ() {
		name, value, ok := strings.Cut(pair, "=")
		if !ok || !strings.HasPrefix(name, "CAVEMAN_") {
			continue
		}
		renamed := "CSTMAN_" + strings.TrimPrefix(name, "CAVEMAN_")
		if _, exists := os.LookupEnv(renamed); !exists {
			_ = os.Setenv(renamed, value)
		}
	}
	if _, exists := os.LookupEnv("CSTMAN_HOME"); exists {
		return
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return
	}
	current := filepath.Join(home, ".cstman")
	legacy := filepath.Join(home, ".caveman")
	if _, err := os.Stat(current); err == nil {
		return
	}
	if info, err := os.Stat(legacy); err == nil && info.IsDir() {
		_ = os.Setenv("CSTMAN_HOME", legacy)
	}
}

func init() { Apply() }
