// Package proxy is the public, byte-safe CSTMAN reverse proxy: the `cstman`
// binary's standalone mode. It swaps a provider base URL for a local listener,
// applies the same byte-safe provider-native transforms as the managed gateway
// (record mode is always pass-through), and records truthful per-request spend
// to a local store labeled `inferred` — never `verified`.
//
// The request lifecycle and provider adapters live under this module:
//   - providers/        the byte-safe adapter set (shared with the managed gateway)
//   - internal/gateway/  the request loop, behind injected auth + telemetry
//   - internal/config/   cstman.yaml + BYOK env-key resolution
//   - internal/store/    the ~/.cstman/ SQLite spend store
//   - cmd/cstman-proxy/ the standalone binary
package proxy

// DefaultListenAddr is where standalone mode binds by default; `cstman start`
// launches the proxy here and `cstman wrap` points agents at it.
const DefaultListenAddr = "127.0.0.1:8787"
