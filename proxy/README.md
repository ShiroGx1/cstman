# CSTMAN Gateway — the public, byte-safe `cstman` standalone gateway.

A base-URL-swap reverse proxy: point an agent at `http://127.0.0.1:8787` and its
LLM traffic flows through CSTMAN with no code change. Single-operator, BYOK, zero
cloud dependencies. Record mode is always a pass-through; on any transform problem
the original bytes are forwarded unchanged. Standalone records truthful per-request
spend to `~/.cstman/cstman.db` and only ever labels savings `inferred` — never
`verified`.

Source and binaries ship under Apache-2.0. See `LICENSE` and `../LICENSING.md`.

```bash
go build ./proxy/...                 # build
ANTHROPIC_API_KEY=… cstman-proxy    # serve on 127.0.0.1:8787
cstman-proxy stats                  # print the local spend summary as JSON
```

## Shared / VPC deployment

The same binary runs as one shared service for a team. `CSTMAN_AUTH_TOKEN` is
the gate: set it and a non-loopback listen address is accepted, and every request
must then carry the token in `x-cave-api-key` or `Authorization: Bearer`. The
proxy consumes that header before resolving the provider credential, so the
shared token is never forwarded upstream. Without the token a non-loopback listen
address is still refused. Provider keys live on the server; Bedrock can use the
task/pod/instance role instead.

```bash
docker run -d -p 8787:8787 -v cstman-data:/data \
  -e CSTMAN_AUTH_TOKEN="$(openssl rand -hex 32)" -e ANTHROPIC_API_KEY=… \
  ghcr.io/juliusbrussee/cstman-proxy:bin-v1.1.7
```

See `../docs/technical/deploy.md` for Compose, ECS, Kubernetes, Cloud Run, and
Fly.io recipes.

Bedrock Runtime is first-party in standalone mode; no raw endpoint is required.
Use either the low-friction bearer key or a complete IAM pair:

```bash
AWS_REGION=us-east-1 AWS_BEARER_TOKEN_BEDROCK=… cstman-proxy
# or:
AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=… AWS_SECRET_ACCESS_KEY=… cstman-proxy
```

`AWS_SESSION_TOKEN` is honored for temporary IAM credentials. Credential
precedence is an explicit inbound credential, then the Bedrock bearer token,
then a complete IAM pair. A partial pair fails closed. Region precedence is
`providers.bedrock.region` in `cstman.yaml`, `CAVE_BEDROCK_REGION`,
`AWS_REGION`, `AWS_DEFAULT_REGION`, then `us-east-1`.

Inbound Bedrock `x-api-key` and bearer credentials are stamped as Bedrock API
keys before auth-mode classification. A Claude Code user agent therefore cannot
relabel paid Bedrock traffic as subscription traffic.

## Codex on a ChatGPT login (`/chatgpt`)

`cstman enable codex` (or `cstman codex`) points Codex at `/chatgpt` and starts
this proxy with recovery confirmed whenever the cstman MCP server is installed.
A `cstman-proxy` you start yourself compresses `/chatgpt` traffic only when it
can prove the agent can fetch elided content back. Either start it with
`CSTMAN_MODE=compress CSTMAN_RECOVERY=mcp` (and keep the cstman MCP server
registered in Codex), or let each request carry CSTMAN's
`mcp__cstman__cstman_retrieve` tool, top-level or in Codex's `additional_tools`
input item. Without either, every request forwards unchanged.

zstd request bodies (Codex's default) are decoded, compressed and re-encoded.
A body that does not decode, or does not shrink, goes out as the exact original
bytes. When a request could have been compressed and was not, the
`chatgpt_proxy` log line says why in `skip_reason`.

Driven by the `cstman` CLI: `cstman start` launches this binary, `cstman wrap
<agent>` points the agent's provider-specific base URL at it. A Bedrock Claude
Code wrap preserves the local AWS BYOK environment. Against a managed gateway it
adds the CSTMAN project key through Claude Code's custom-header seam; the
gateway resolves the project's stored Bedrock credential when the child has no
AWS credential. When the environment does contain a bearer key or complete IAM
tuple, wrap forwards it ephemerally as `x-cave-upstream-key` (bearer first;
IAM encoded as
`AWS_ACCESS_KEY_ID:AWS_SECRET_ACCESS_KEY[:AWS_SESSION_TOKEN]`). Newlines and
incomplete IAM environments fail before launch.

Runtime is the default Bedrock lane. Mantle's Anthropic Messages-compatible
route is separate, uses `/bedrock/anthropic`, and remains disabled unless the
deployment explicitly enables `CAVE_BEDROCK_MANTLE_ENABLED`.

The byte-safe provider adapters under `providers/` are shared with the managed
gateway, which imports them from here.
