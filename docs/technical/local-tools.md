# Local tools

CSTMAN ships local tools for recovery, memory, browser context, and large
command output. They work without a CSTMAN account.

## MCP server

Register recovery server with detected agents:

```bash
cstman tools mcp install
```

Run `cstman tools mcp uninstall` to remove registration. Direct server binary,
`cstman-mcp`, communicates over standard input and output.

It exposes five tool classes:

| Tool | Purpose |
|---|---|
| Compress | Reduce eligible context and return recovery reference |
| Retrieve | Fetch exact source for a recovery handle |
| Stats | Read local compression statistics |
| TOON encode | Encode supported structured input |
| TOON decode | Decode and validate TOON input |

MCP transport is local process I/O, and host agent decides when tools can be
called. Configure its tool permissions as narrowly as possible.

## Cavemem

Cavemem stores durable project facts in SQLite and retrieves them with local
BM25 text ranking.

Main operations:

```bash
cstman tools mem remember "fact"
cstman tools mem recall "query"
cstman tools mem supersede <id> "replacement"
cstman tools mem history <id>
cstman tools mem forget <id>
```

`remember` and `supersede` also accept `--stdin` in place of the text argument,
which is the only way to store a fact larger than one command-line argument
allows (about 128 KB on Linux, and a 32 KB whole command line on Windows).
`supersede --stdin` needs a cavemem build that lists the `supersede-stdin`
capability in `cavemem version --json`; an older one is refused rather than
sent text it would misread, so upgrade the binary if you see that message.

Recall returns current facts by default and has a default inferred-token budget
of 2,000. Superseded history remains available for inspection. Recalled compact
records can include recovery references to exact stored source.

Memory is local persistence, not model training. A remembered statement can be
wrong or stale; source and supersession metadata help callers judge it.

Build standalone binary:

```bash
go build -o cavemem ./mem/cmd/cavemem
```

## Browser bridge

Browser bridge attaches to Chrome through Chrome DevTools Protocol. It captures
an accessibility-tree representation, filters it by query, compresses it, and
returns actionable element references.

```bash
cstman tools browse https://example.com "pricing"
cstman tools browse act '<reference>' click
cstman tools browse eval 'document.title'
cstman tools browse recover '<handle>'
cstman tools browse close
```

Snapshots avoid screenshots when semantic structure is enough. Recovery keeps
exact captured source available. Browser actions and JavaScript evaluation can
change page or account state; host permission policy should distinguish read
and write operations.

Build bridge:

```bash
go build ./browse/cmd/cstman-browse
```

## Output shrinker

Output shrinker parses large command and tool results, keeps high-signal
structure, and stores full source in CCR. It is useful for compiler logs, test
output, diffs, search results, and terminal transcripts.

```bash
some-command | cstman tools shrink
cstman tools shrink -- go test ./...
```

Structural shrink input is capped at 32 MiB. CLI command capture uses a separate
bounded limit, 8 MiB by default. Oversized input is rejected or handled by
caller policy; it is not silently treated as complete.

Shrinker must preserve error class, exit status, relevant paths, and recovery
handle. A short summary without those fields is not a safe replacement for
debugging output.

## Tool-catalog shrinker

`cstman-shrink` specializes in MCP and OpenAI-style tool catalogs. It keeps
tool names, parameters, enums, required fields, defaults, constants, and `$ref`
targets while removing annotations and shortening long descriptions. Description
reduction remains lossy and can change tool selection.

```bash
cat tools.json | cstman-shrink > tools.min.json
cstman-shrink lint tools.json
cstman-shrink recover <handle> > tools.original.json
```

Input cap is 32 MiB. Malformed or non-winning input passes through. Exact source
must be committed to CCR before compact catalog and handle are emitted.

## Local storage

Local proxy and tools commonly use:

```text
~/.cstman/cstman.db
~/.cstman/ccr.db
~/.cstman/mem/mem.db
~/.cstman/mem/ccr.db
~/.cstman/cstman.yaml
~/.cstman-cloud/config.json
```

Project overlays use `./.cstman/config.json`. Back up or delete these files only
with awareness that recovery handles and learned observations may stop resolving,
along with local memory.
