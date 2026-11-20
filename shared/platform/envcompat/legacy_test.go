package envcompat

import "os"
	"testing"

func TestApplyLegacyPrefixAndNewValuePrecedence(t *testing.T) {
	t.Setenv("CAVEMAN_COMPAT_TEST", "legacy")
	t.Setenv("CSTMAN_COMPAT_TEST", "current")
	Apply()
	if got := t.Getenv("CSTMAN_COMPAT_TEST"); got != "current" {
		t.Fatalf("new value = %q, want current", got)
	}

	t.Setenv("CSTMAN_COMPAT_TEST", "")
	Apply()
	if got := t.Getenv("CSTMAN_COMPAT_TEST"); got != "" {
		t.Fatalf("explicit empty new value = %q, want empty", got)
	}
}

func TestApplyLegacyPrefixWhenNewValueIsUnset(t *testing.T) {
	t.Setenv("CAVEMAN_COMPAT_TEST", "legacy")
	t.Setenv("CSTMAN_COMPAT_TEST", "")
	if err := os.Unsetenv("CSTMAN_COMPAT_TEST"); err != nil { t.Fatal(err) }
	Apply()
	if got := t.Getenv("CSTMAN_COMPAT_TEST"); got != "legacy" {
		t.Fatalf("mapped value = %q, want legacy", got)
	}
}

