# syntax=docker/dockerfile:1

# Build stage runs on the BUILDER's architecture and cross-compiles with the Go
# toolchain, so multi-arch images need no QEMU. The runtime stage has no RUN, so
# nothing ever has to execute a foreign-arch binary during the build.
# Base images are pinned by digest (the tag stays for readability); Dependabot's
# docker ecosystem proposes digest bumps.
FROM --platform=$BUILDPLATFORM golang:1.27.3-alpine@sha256:d200d2dd76b03a99b52651fd1325aff7dcd35422c35c01bac56571b0507f3deb AS build
ARG TARGETOS
ARG TARGETARCH
ARG VERSION=dev
WORKDIR /src

COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go mod download

# The binary's entire in-module import closure (verified with `go list -deps`).
# Both committed asset sets it embeds — proxy/internal/nativepack/native-pack.generated.json
# and engine/pixel/assets/*.bin.gz — come along with these directories.
COPY engine/ engine/
COPY mem/ mem/
COPY proxy/ proxy/
COPY shared/ shared/

# CGO_ENABLED=0: unlike the release cstman-proxy (cgo via zig, see
# scripts/build-release-binaries.mjs), the image's code compressor parses Go only.
# -buildvcs=false because .dockerignore keeps .git out of the build context.
# -X main.version stamps `var version = "dev"` in proxy/cmd/cstman-proxy/main.go.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -buildvcs=false \
      -ldflags "-s -w -X main.version=$VERSION" \
      -o /out/cstman-proxy ./proxy/cmd/cstman-proxy \
 && mkdir -p /out/data

# License texts of the third-party Go modules the binary links, and the Go
# runtime's, for /licenses. go-licenses is pinned and runs on the build
# platform; GOOS/GOARCH select the target's build tags.
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    GOBIN=/tmp/bin go install github.com/google/go-licenses/v2@v2.0.1 \
 && CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH /tmp/bin/go-licenses save ./proxy/cmd/cstman-proxy \
      --ignore github.com/JuliusBrussee/cstman --save_path /out/licenses/third_party \
 && mkdir -p /out/licenses/third_party/go.dev/go \
 && cp "$(go env GOROOT)/LICENSE" /out/licenses/third_party/go.dev/go/LICENSE

# distroless static: CA roots for outbound provider TLS, no shell, no package
# manager, nothing to exploit. The :nonroot tag already runs as uid 65532.
FROM gcr.io/distroless/static-debian12:nonroot@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab
# release-binaries.yml passes the tag, commit, and repository URL.
ARG VERSION=dev
ARG REVISION=unknown
ARG SOURCE=https://github.com/JuliusBrussee/cstman
LABEL org.opencontainers.image.title="cstman-proxy" \
      org.opencontainers.image.description="CSTMAN local compression proxy and middleware runtime" \
      org.opencontainers.image.source="$SOURCE" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION" \
      org.opencontainers.image.licenses="MIT"
COPY --from=build /out/cstman-proxy /cstman-proxy
# The binary is MIT and embeds separately licensed pixel and font assets;
# their license texts and notices ship with every copy.
COPY LICENSE LICENSE-MIT NOTICE LICENSING.md /licenses/
COPY engine/pixel/NOTICE /licenses/NOTICE.engine-pixel
COPY engine/pixel/assets/SPLEEN_LICENSE.txt engine/pixel/assets/UNIFONT_LICENSE.txt /licenses/
COPY --from=build /out/licenses/third_party /licenses/third_party/
# An empty, correctly-owned /data so a named or anonymous volume inherits uid
# 65532. A BIND mount does NOT inherit it — chown the host directory to 65532
# yourself or the proxy cannot create its SQLite spend store under CSTMAN_HOME.
COPY --from=build --chown=nonroot:nonroot /out/data /data
# Implied by the :nonroot tag; stated so the security posture is visible here.
USER nonroot
ENV CSTMAN_HOME=/data \
    CSTMAN_LISTEN=0.0.0.0:8787
VOLUME /data
EXPOSE 8787
# No HEALTHCHECK instruction: the image has no shell and no curl to run one.
# Probe GET /health/ready (or /health/live) on 8787 from the orchestrator —
# Kubernetes httpGet, an ALB target group, or an external compose checker.
ENTRYPOINT ["/cstman-proxy"]
CMD ["serve"]
