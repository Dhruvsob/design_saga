FROM golang:1.26.10-bookworm@sha256:5de7c99eb78ca5e515a4c340235d0955ec5964a5071c492c15503d7c267da473 AS builder

# Rebuild the released FerretDB 2.7.0 source with a patched Go standard
# library. Keep the application source and module graph unchanged; the commit
# check prevents a moved tag or unreviewed branch from entering the image.
RUN git clone --quiet https://github.com/FerretDB/FerretDB.git /src \
    && cd /src \
    && git checkout --quiet 0d5eb3343a50b800634cc08ace608bb6f3a3f74b \
    && test "$(git rev-parse HEAD)" = "0d5eb3343a50b800634cc08ace608bb6f3a3f74b"

WORKDIR /src
COPY deploy/ferretdb/mcp-v1.patch /tmp/mcp-v1.patch
RUN git apply --check /tmp/mcp-v1.patch \
    && git apply /tmp/mcp-v1.patch

ENV CGO_ENABLED=0 \
    GOAMD64=v1
RUN /usr/local/go/bin/go get \
        github.com/jackc/pgx/v5@v5.9.0 \
        github.com/klauspost/compress@v1.18.7 \
        github.com/modelcontextprotocol/go-sdk@v1.4.1 \
        go.opentelemetry.io/otel@v1.44.0 \
        go.opentelemetry.io/otel/sdk@v1.44.0 \
        go.opentelemetry.io/otel/trace@v1.44.0 \
        go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.44.0 \
        golang.org/x/crypto@v0.58.0 \
        golang.org/x/net@v0.62.0 \
        golang.org/x/text@v0.43.0 \
        google.golang.org/grpc@v1.83.2 \
    && /usr/local/go/bin/go mod tidy \
    && /usr/local/go/bin/go mod download \
    && /usr/local/go/bin/go mod verify \
    && /usr/local/go/bin/go build -trimpath -o /out/ferretdb ./cmd/ferretdb \
    && /out/ferretdb --version \
    && install -d -o 1000 -g 1000 /out/state

FROM scratch

COPY --from=builder /src/build/ferretdb/passwd /etc/passwd
COPY --from=builder /src/build/ferretdb/group /etc/group
COPY --from=builder /out/ferretdb /ferretdb
COPY --from=builder --chown=1000:1000 /out/state /state

USER ferretdb:ferretdb
ENTRYPOINT ["/ferretdb"]
HEALTHCHECK --interval=1m --timeout=5s --retries=1 --start-period=30s --start-interval=5s CMD ["/ferretdb", "ping"]
WORKDIR /
VOLUME /state
EXPOSE 27017 27018 8088

ENV FERRETDB_LISTEN_ADDR=:27017 \
    FERRETDB_DEBUG_ADDR=:8088 \
    FERRETDB_STATE_DIR=/state

LABEL org.opencontainers.image.description="FerretDB 2.7.0 rebuilt with a patched Go runtime" \
      org.opencontainers.image.revision="0d5eb3343a50b800634cc08ace608bb6f3a3f74b" \
      org.opencontainers.image.source="https://github.com/FerretDB/FerretDB" \
      org.opencontainers.image.title="FerretDB" \
      org.opencontainers.image.vendor="FerretDB Inc." \
      org.opencontainers.image.version="v2.7.0-security-rebuild"
