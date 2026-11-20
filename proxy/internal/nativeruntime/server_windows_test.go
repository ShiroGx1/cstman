//go:build windows

package nativeruntime

import (
	"strings"
	"testing"
)

func TestSocketPathWindowsIsPerInstall(t *testing.T) {
	one := SocketPath(`C:\Users\Alice\.cstman`)
	two := SocketPath(`C:\Users\Bob\.cstman`)
	if !strings.HasPrefix(one, `\\.\pipe\cstman-native-`) {
		t.Fatalf("SocketPath() = %q", one)
	}
	if one == two {
		t.Fatal("different installs must not share a pipe")
	}
	if one != SocketPath(`c:\users\alice\.cstman\.`) {
		t.Fatal("equivalent case-insensitive Windows paths must share a pipe")
	}
}

// Same vector as packages/cli/tests/windows-platform.runtime.mjs. JavaScript's
// toLowerCase turns İ into two code points and a word-final Σ into ς, so a
// Node hook that folds differently dials a pipe nothing listens on.
func TestSocketPathWindowsMatchesNodeAdapters(t *testing.T) {
	for home, want := range map[string]string{
		`C:\Users\İlker\ΝΙΚΟΣ\.cstman`: `\\.\pipe\cstman-native-4f3f9f7846224643`,
		`C:\Users\Jane Doe\.cstman`:    `\\.\pipe\cstman-native-0b9a73ef77a5671a`,
	} {
		if got := SocketPath(home); got != want {
			t.Fatalf("SocketPath(%q) = %q, want %q", home, got, want)
		}
	}
}
