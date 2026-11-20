# CSTMAN

<p align="center"><img src="docs/assets/cstman-logo.png" alt="CSTMAN logo" width="760"></p>

CSTMAN is a local toolkit for coding-agent workflows. This repository combines a command-line interface, reusable agent skills, and companion runtime components.

## What is included

- `packages/cli` — the Node.js command-line client.
- `skills/` — the main CSTMAN skill router and focused skills for common tasks.
- `engine/`, `proxy/`, `mcp/`, `browse/`, `mem/`, and `shrink/` — local runtime and tool sources.
- `packages/` — SDKs, middleware, and shared contracts.

The local tools support agent setup, context recovery, command-output compression, and usage inspection. Optional hosted services are separate.

## Install

After this fork's npm package is released:

```bash
npx cstman@latest
```

Then check the runtime and integrations:

```bash
cstman setup
cstman setup --install
```

Some features need the companion runtime. `cstman setup` reports what is installed and what is missing.

## Common commands

```bash
cstman --help
cstman status
cstman shrink -- <command>
cstman learn
```

Run `cstman <command> --help` for command options. The primary skill entry is [`skills/cstman/SKILL.md`](skills/cstman/SKILL.md); specialized skills remain in sibling folders under `skills/`.

<!-- BENCHMARK-TABLE-START -->
<!-- BENCHMARK-TABLE-END -->

## Build from source

Requirements: Node.js 22.13 or newer and pnpm 10.14. Go is needed when building the companion runtimes.

```bash
corepack enable
pnpm install
pnpm --dir packages/cli build
pnpm --dir packages/cli test
```

## Copyright and license

Copyright (c) 2026 ShiroGx1. First-party source in this fork is licensed under MIT; see [`LICENSE`](LICENSE) and [`LICENSING.md`](LICENSING.md). Third-party components retain their own license terms, listed in [`NOTICE`](NOTICE). This is a community fork; see [`TRADEMARKS.md`](TRADEMARKS.md) for name and logo usage.
