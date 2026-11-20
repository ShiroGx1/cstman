package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"

	"github.com/JuliusBrussee/cstman/proxy/internal/pool"
	"github.com/JuliusBrussee/cstman/shared/platform/env"
)

// runProviderLogin is `cstman providers login <provider>`: the subscription
// logins whose terms allow a third-party client. Only Sign in with ChatGPT
// today (experimental); API keys are added by the CLI itself.
func runProviderLogin(args []string) {
	if len(args) != 1 || args[0] != "chatgpt" {
		fmt.Fprintln(os.Stderr, "usage: cstman-proxy provider-login chatgpt")
		os.Exit(2)
	}
	home := env.String("CSTMAN_HOME", "")
	if home == "" {
		userHome, err := os.UserHomeDir()
		if err != nil {
			fmt.Fprintln(os.Stderr, "cstman: no home directory")
			os.Exit(1)
		}
		home = filepath.Join(userHome, ".cstman")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	if err := pool.NewStore(home).LoginChatGPT(ctx, pool.LoginOptions{Out: os.Stderr}); err != nil {
		fmt.Fprintln(os.Stderr, "cstman: "+err.Error())
		os.Exit(1)
	}
	fmt.Fprintln(os.Stderr, "Signed in with ChatGPT. Routing may now send requests to your ChatGPT plan, straight from this machine.")
}
