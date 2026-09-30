# Design Saga VPS deployment

The application follows `https://github.com/Dhruvsob/design_saga.git` and stores
its data in PostgreSQL 17 through FerretDB and the DocumentDB extension. Only
Nginx is exposed to the internet; FastAPI, FerretDB, and PostgreSQL remain on
the private Compose network.

## Update from GitHub

The Hostinger checkout is on the `production` branch. It keeps one local commit
containing Docker, PostgreSQL, and HTTP compatibility changes on top of GitHub
`main`. The checkout is configured to rebase its production commits whenever it
pulls.

```bash
cd /opt/design-saga-git
git pull
```

The installed Git hooks call `deploy/redeploy.sh` after a successful merge or
rebase, rebuilding and restarting the application automatically. If Git reports
a rebase conflict, stop and resolve it before rebuilding; do not force-reset the
branch because that would discard the production layer.

## Manual deployment

```bash
docker compose up -d --build
docker compose ps
curl -fsS https://gamaa.in/api/
```

Caddy serves `gamaa.in` and `www.gamaa.in`, redirects HTTP to HTTPS, and renews
the TLS certificates automatically. The DNS A record for `gamaa.in` must point
to `187.52.124.46`; `www` can be a CNAME to `gamaa.in`.

Keep `COOKIE_SECURE=true` in production. Never run `docker compose down -v`;
the `-v` option deletes both the PostgreSQL data volume and Caddy certificate
state.
