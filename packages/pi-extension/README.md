# @cstman-ai/pi

Native [CSTMAN](https://getcaveman.dev) extension for the [Pi coding agent](https://pi.dev).

One extension, four jobs:

- **Proxy routing** — points the selected model's provider at your local CSTMAN
  proxy (`/w/pi/...`) by updating that model's endpoint and preserving the SDK's
  original URL-dependent compatibility settings. Pi keeps owning auth, model
  names, pricing, and `models.json`; the provider registry is unchanged. The
  extension routes only when the running proxy identifies the same destination:
  scheme, host, port, path, and API version must match. Custom providers need a
  published `compat.<provider>.base_url` mount. The proxy's live identity must
  also match its run-state file. Unknown endpoints and older proxies without
  this proof stay direct with a notice. Pi keeps its own provider identity,
  model catalog, auth registration, and custom stream handlers.
  OpenAI Chat Completions endpoints containing `api.openai.com` stay direct:
  Pi derives their prompt cache key from the URL and exposes no reliable
  override for routed requests. OpenAI Responses routing remains supported.
  Pi also derives attribution/session headers from some URLs. OpenRouter,
  NVIDIA, Cloudflare, and OpenCode aliases stay direct when their original
  headers cannot be preserved; canonical provider IDs remain routable. An alias
  can route when explicit headers make the result identical, or when
  `PI_TELEMETRY=0` disables the affected attribution (OpenCode session headers
  still require preservation). The extension does not reload or guess Pi's
  private active telemetry preference.

- **Exact recovery** — registers a single model-visible tool, `cstman_retrieve`,
  backed by the local `cstman-mcp` binary and the shared CCR store. Before
  shortening a tool result, the extension checks that its advertised handle
  resolves to the original bytes without consuming the model's later recovery.
  Missing, mismatched, or unverifiable handles leave the original output intact.
  Older companions without verification support keep tool results unchanged. A
  session that cannot call `cstman_retrieve` leaves results unchanged as well —
  `pi --tools …` without it, or a subagent with its own `tools:` list, replaces
  the active tool set, and a handle the model cannot redeem would lose the
  output instead of compressing it.
- **Native lifecycle** — bridges Pi session/turn/tool events into the CSTMAN
  native runtime (Core injection, per-turn context, tool-output shrinking).
- **Honest fallback** — routing activates only after the recovery gate holds
  (proxy alive, recovery contract matched, MCP child initialized). Anything else
  is a visible pass-through: direct provider, one notice, no savings claims.
  OAuth/subscription models stay direct unless the running proxy explicitly
  advertises a verified subscription route. Pi's built-in `openai-codex`
  ChatGPT Responses provider is supported; other OAuth providers remain direct.

## Install

Through the CSTMAN CLI (recommended — journaled, reversible):

```bash
cstman wrap pi      # this session only
cstman enable pi    # persistent; plain `pi` stays routed until `cstman disable pi`
```

Or as a plain Pi package. Use this or `cstman enable pi`, not both: Pi refuses
to start when two copies register the same tool.

```bash
pi install npm:@cstman-ai/pi
```

Requires the CSTMAN CLI (`npm i -g cstman`) plus the local
`cstman-proxy` / `cstman-mcp` binaries (`cstman setup`). Without them the
extension loads, says so once, and stays out of the way.

Pinned against `@earendil-works/pi-coding-agent` 1.0.4.
