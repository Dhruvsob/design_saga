# Design Saga VPS deployment

The application follows `https://github.com/Dhruvsob/design_saga.git` and stores
its data in PostgreSQL 17 through FerretDB and the DocumentDB extension. Only
Nginx is exposed to the internet; FastAPI, FerretDB, and PostgreSQL remain on
the private Compose network.

## Update from GitHub

The Hostinger checkout is on the `production` branch. It keeps one local commit
containing Docker, PostgreSQL, and HTTP compatibility changes on top of GitHub
`main`. The checkout is configured to rebase that commit whenever it pulls.

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
curl -fsS http://127.0.0.1/api/
```

Keep `COOKIE_SECURE=false` while accessing the server by HTTP IP. Set it to
`true` after a domain and HTTPS are configured. Never run
`docker compose down -v`; the `-v` option deletes the PostgreSQL volume.
