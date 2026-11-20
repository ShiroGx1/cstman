# cstman-mcp

The CSTMAN MCP server: five compression tools — `cstman_compress`,
`cstman_retrieve`, `cstman_stats`, `cstman_toon_encode`, and
`cstman_toon_decode` — over stdio, for any MCP host. It links the
[CSTMAN Engine](../engine) in-process. **Local-only** (opens no
network connection) and **inferred-only** (it never claims `verified` savings).

## Install (Claude Code)

```jsonc
// .mcp.json / claude mcp config
{
  "mcpServers": {
    "cstman": { "command": "npx", "args": ["-y", "cstman-mcp"] }
  }
}
```

The launcher downloads matching binary on first run, verifies
key-signed checksum manifest plus artifact SHA-256, and caches it under
`~/.cstman/bin`. No Go toolchain or global CSTMAN install is required.
To use an existing reviewed binary instead:

```bash
CSTMAN_MCP_BIN=/path/to/cstman-mcp npx cstman-mcp
```

npm launcher and downloaded binary are both Apache-2.0; see `BINARY_LICENSE.md`.

## Tools

| Tool | Input | Returns |
|---|---|---|
| `cstman_compress` | `input` (string) | compressed text, inferred `ratio`, `recovery_handle` (null on pass-through) |
| `cstman_retrieve` | `recovery_handle` (string), optional `query` | byte-exact original without a query; ranked complete records with a query; error on unknown handle |
| `cstman_stats` | — | this MCP process's compression-call totals, including repeated inputs and pass-throughs: tokens before/after, `requests`, `ratio`, `basis:"inferred"`, `scope:"session"` |
| `cstman_toon_encode` | `input` (JSON string) | explicit JSON→TOON result with sizes; pass-through plus note when not encodable |
| `cstman_toon_decode` | `input` (TOON string) | decoded JSON; error on invalid TOON |

Compression is lossy (S4) but **reversible**: every drop is recoverable via
`cstman_retrieve`. Incompressible or malformed input passes through unchanged
with `ratio:0` — never an error.

Repeated recovery calls remain available after host compaction. An empty query
returns the exact stored original on every call; a nonempty query keeps the same
record-narrowing behavior regardless of how many earlier calls were made.

Hosts that publish compressed output can first call `cstman_retrieve` with
`{"recovery_handle":"ccr://ccr_…","verify_only":true}`. Check for the
`recovery_verification` capability in `cstman-mcp version --json` before using
this optional mode: older servers may ignore unknown arguments.

Verification returns a JSON text block containing the normalized bare
`recovery_handle`, UTF-8 `byte_length`, and lowercase hexadecimal `sha256` of
the complete stored original. It ignores `query`, errors on unknown handles,
and does not count as a delivery. Compare all three fields with the proposed handle and original bytes;
retain the original output when verification fails. This checks availability
at publication time, not indefinite retention or immunity to later deletion.
