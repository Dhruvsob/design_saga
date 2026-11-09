FROM golang:1.26.10-bookworm@sha256:5de7c99eb78ca5e515a4c340235d0955ec5964a5071c492c15503d7c267da473 AS gosu-builder

# The upstream DocumentDB image ships gosu 1.19 built with an old Go
# standard library. Rebuild the same reviewed gosu release from its pinned
# commit so the database entrypoint retains identical behaviour without the
# fixed stdlib vulnerabilities in the published binary.
RUN git clone --quiet https://github.com/tianon/gosu.git /src/gosu \
    && cd /src/gosu \
    && git checkout --quiet 6456aaa0f3c854d199d0f037f068eb97515b7513 \
    && test "$(git rev-parse HEAD)" = "6456aaa0f3c854d199d0f037f068eb97515b7513" \
    && CGO_ENABLED=0 /usr/local/go/bin/go build \
        -trimpath -ldflags="-s -w" -o /out/gosu . \
    && /out/gosu --version

FROM ghcr.io/ferretdb/postgres-documentdb:17-0.107.0-ferretdb-2.7.0@sha256:2386795ec2aa7ae559304361979f1dc5708d383ee9020ae63dadc2940dfe58f7

# FerretDB 2.7 is the latest released compatible application version, but its
# pinned DocumentDB image was published with old Debian security packages.
# Keep the extension/version pair unchanged and apply current Debian patches at
# build time. The release gate scans this derived runtime before deployment.
USER root
COPY --from=gosu-builder /out/gosu /usr/local/bin/gosu
# Keep the PostGIS shared library and extension scripts on the same version.
# apt-get upgrade otherwise holds the library while upgrading its scripts,
# which prevents DocumentDB from initializing.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get -y upgrade \
    && DEBIAN_FRONTEND=noninteractive apt-get -y install --only-upgrade \
        postgresql-17-postgis-3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
