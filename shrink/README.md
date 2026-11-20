# cstman-shrink

Compress MCP/OpenAI **tool catalogs** so a large tool list costs fewer tokens.
It drops annotation bloat (examples, titles, comments, schema markers), reduces
long descriptions while retaining recognised constraint-bearing sentences, and
keeps the structural selection surface plus argument-construction values
(`default`, `const`, `$ref` targets) byte-for-byte. Description reduction is
model-visible and lossy: structural preservation does not guarantee the model
will pick the same tool. All numbers are `inferred`.

## Use

```bash
# Compress a catalog (stdin → stdout); the inferred ratio report goes to stderr.
cat tools.json | cstman-shrink > tools.min.json

# Recover exact original bytes from a handle printed in shrink's stderr report.
cstman-shrink recover ccr_... > tools.original.json

# Inspect the per-tool reduction without committing to it.
cstman-shrink lint tools.json
```

Launcher downloads matching binary on first run, verifies
key-signed checksum manifest plus artifact SHA-256, and caches it under
`~/.cstman/bin`. No Go toolchain or global CSTMAN install is required:

```bash
npx -y cstman-shrink lint tools.json
```

npm launcher and downloaded binary are both MIT; see `BINARY_LICENSE.md`.

## Guarantees

- **Structural selection surface** — the compressed catalog exposes the exact
  same names/params/enums/required as the original. Same-tool behavior needs a
  model eval; this structural check alone cannot prove it.
- **Argument-construction preservation** — short descriptions remain whole;
  long descriptions retain their lead plus recognised constraint sentences.
  Defaults, constants, and internal reference targets survive.
- **Fail-open** — successful compression is S4 and model-visible; malformed or
  incompressible input passes through unchanged.
- **Bounded input** — stdin is capped at 32 MiB. Larger catalogs fail with
  `cave_input_too_large`; they are not buffered without limit.
- **Reversible** — a compressing shrink commits exact original bytes to
  `CSTMAN_CCR_DB` (or `~/.cstman/ccr.db`) before returning its handle; a later
  process resolves it with `cstman-shrink recover`.
