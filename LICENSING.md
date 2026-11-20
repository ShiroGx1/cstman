# CSTMAN Licensing

The first-party source in this fork is licensed under the MIT License in the
root `LICENSE`, Copyright (c) 2026 ShiroGx1. This applies to the repository's
source and published packages. Third-party components retain their own license
terms; their notices remain in `NOTICE` and package-specific files.

CSTMAN Cloud is separate commercial software and is not included here. Releases
published by the upstream project before this fork retain the terms they shipped
with; this repository's source is MIT-licensed.

## License files

- Root `LICENSE` contains this fork's MIT license.
- Project package `LICENSE` and `LICENSE.*` files copy the root license.
- `LICENSE-MIT` preserves the historical MIT text referenced by upstream
  notices. `NOTICE` retains upstream copyright and third-party attributions.

## Contributions

Contributions to this repository are licensed under MIT. See
`CONTRIBUTING.md`.

## Third-party code

`engine/pixel/` is a Go port of pxpipe (MIT, Copyright (c) 2026
claude-image-proxy contributors) with embedded glyph atlases derived from the
Spleen 5x8 (BSD-2-Clause) and GNU Unifont (OFL-1.1 / GPLv2 with font-embedding
exception) fonts. The upstream MIT and font notices are preserved in
`engine/pixel/NOTICE` and `engine/pixel/assets/`.

`browse/` links MIT-licensed chromedp modules; see `browse/NOTICE`.

The runtime binaries and container image link third-party Go modules (MIT,
BSD-3-Clause, Apache-2.0); every binary release ships their license texts as
`THIRD_PARTY_GO_LICENSES.tar.gz`, and the image under `/licenses/third_party/`.
The release `cstman-proxy` and `cstman-engine` are built with `zig cc` and
statically link Zig's compiler runtime (MIT), musl libc on Linux (MIT), and the
mingw-w64 runtime on Windows (ZPL-2.1); their notices ship as `LICENSE.zig`,
`COPYRIGHT.musl` and `COPYING.mingw-w64`.
The CLI contains a port of part of Qwen Code (Apache-2.0) and bundles
MIT-licensed `@clack/prompts` and its dependencies; see `packages/cli/NOTICE`.
The extension ships the Geist fonts under the SIL Open Font License 1.1
(`extension/fonts/GEIST_LICENSE.txt`).

## Trademarks

"CSTMAN" and CSTMAN logos are trademarks of Julius Brussee. MIT grants no
trademark rights. Nominative use such as "Powered by CSTMAN" or "Optimized by
CSTMAN" is allowed when truthful. Naming a product, hosted service, or fork in
a way that implies CSTMAN sponsorship requires written permission.

See `TRADEMARKS.md` for the full trademark policy.