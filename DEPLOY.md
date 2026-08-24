# Deployment guide

Launch Tracker — internal deployment. Written for whoever is standing this up,
which may not be its author.

---

## The one thing that matters

**Everything the application writes lives in `/app/data`** — the SQLite
database, the audit log, and the backup snapshots.

That path **must be a mounted volume**. If it stays inside the container, it
is destroyed on every redeploy. The application will appear to work perfectly
and then silently lose every gate date entered since the last deployment.
Nobody notices at the time.

The supplied `docker-compose.yml` already does this correctly. If you deploy
some other way, this is the line to carry across.

---

## Quick start

```bash
git clone <repo-url> launch-tracker
cd launch-tracker

export APP_PASSWORD_VIEWER='...'      # read-only access
export APP_PASSWORD_EDITOR='...'      # can add and edit records

docker compose up -d --build
```

Then open `http://<host>:8501`.

The application refuses to start if neither password is set — it fails closed
rather than serving openly.

---

## Configuration

All configuration is environment variables. Nothing needs editing inside the
image.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `APP_PASSWORD_VIEWER` | yes | — | Read-only access |
| `APP_PASSWORD_EDITOR` | yes | — | Add and edit records |
| `TRACKER_SNAPSHOT_HOURS` | no | `24` | Backup interval. **Set to `1`** — hourly caps how much work a failure can destroy |
| `TRACKER_BACKUP_DIR` | no | unset | Path to mirror snapshots to, off this host |
| `TRACKER_KEEP_SNAPSHOTS` | no | `60` | Recent snapshots retained |
| `TRACKER_KEEP_MONTHLY` | no | `24` | First-of-month snapshots retained |

Passwords are read from the environment, or from `.streamlit/secrets.toml` if
one is mounted. The environment is simpler for containers and keeps
credentials off the filesystem. `.streamlit/secrets.toml` is excluded from the
image by `.dockerignore` and can never be baked in accidentally.

---

## Storage

### Named volume (default)

```yaml
volumes:
  - tracker-data:/app/data
```

Managed by Docker. Fine, and the data survives redeploys.

### Host directory (often better)

If the data needs to sit somewhere an existing backup regime already covers:

```yaml
volumes:
  - /srv/launch-tracker/data:/app/data
```

Create it first and make it writable by UID 10001, the unprivileged user the
container runs as:

```bash
sudo mkdir -p /srv/launch-tracker/data
sudo chown -R 10001:10001 /srv/launch-tracker/data
```

### Sizing

Trivial. The database is around 60 KB today and is not expected to exceed
10 MB with several years of history. Backup snapshots are of similar size;
with default retention the whole directory should stay well under 1 GB.

---

## Backups

The application backs itself up. It does not need an external job, though one
can be scheduled if preferred.

- A snapshot is taken on the configured interval, holding both a copy of the
  database and CSV exports of every table.
- Each snapshot verifies its own integrity when written.
- Retention is 60 recent snapshots plus first-of-month for 24 months.
- Backup health — snapshot age, verification result, whether an off-host copy
  exists — is displayed inside the application.

### Getting copies off this host

Either include the data directory in the existing backup regime, **or** mount
a network share and point the application at it:

```yaml
volumes:
  - /mnt/nas/launch-tracker-backups:/mnt/backup
environment:
  TRACKER_BACKUP_DIR: "/mnt/backup"
```

Snapshots are then mirrored there automatically as they are taken.

Backups sitting only on the host they protect are not a backup strategy — they
cover a bad edit, not a lost machine.

### Checking and restoring

```bash
docker compose exec launch-tracker python daily_backup.py --health
docker compose exec launch-tracker python daily_backup.py --verify
docker compose exec launch-tracker python daily_backup.py --list
docker compose exec launch-tracker python daily_backup.py --restore data/backups/daily/2026-08-24
```

Restore is also available inside the application, under
*Data entry → Export and backups*, for anyone with the editor password.

**Please perform one restore on a copy before this carries real data.** A
restore procedure nobody has run is a document, not a capability.

---

## Networking

Single HTTP listener on port 8501. No outbound connections at run time, and
Streamlit's usage telemetry is disabled.

Behind a reverse proxy, Streamlit needs WebSocket upgrade to be passed
through. Minimal nginx:

```nginx
location / {
    proxy_pass         http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host $host;
    proxy_read_timeout 86400;
}
```

If it is served from a subpath rather than a hostname root, add
`--server.baseUrlPath=/launch-tracker` to the command in the Dockerfile.

Health endpoint for load balancers and orchestrators:
`GET /_stcore/health` → `200 ok`. The container healthcheck already uses it.

---

## Operating it

```bash
docker compose logs -f launch-tracker     # logs
docker compose restart launch-tracker     # restart
docker compose up -d --build              # deploy a new version
docker compose ps                         # health status
```

Upgrading is a rebuild. Data is untouched because it lives on the volume — but
take a snapshot first if you want to be certain:

```bash
docker compose exec launch-tracker python daily_backup.py --force
```

---

## Security notes

- Runs as an unprivileged user, UID 10001. Not root.
- `no-new-privileges` is set.
- No credentials in the image; passwords come from the environment.
- No data in the image; `.dockerignore` excludes `data/` and any secrets file.
- No outbound network calls at run time.
- Intended for the internal network only. There is no reason to expose it
  externally.
- Optional read-only root filesystem is included in `docker-compose.yml`,
  commented out. It should work — the application writes nothing outside
  `/app/data` — but it has not been verified, so enable it, confirm the
  container starts and the page loads, then leave it on.

---

## Access model

Two roles behind separate passwords: viewer (read-only) and editor (can add
and change records). Roughly six people need editor access; everyone else is a
viewer.

Every change is written to an append-only audit log with a timestamp, the
role, the field, and both old and new values.

Single sign-on is not implemented. If it is straightforward to put an identity
provider in front of this, that would be an improvement — the audit log would
then name a person rather than a role. It is not a blocker: the application is
internal-only and viewers cannot modify anything.

---

## If something goes wrong

**Container will not start.** Check `docker compose logs`. The most likely
cause is a missing password variable — the app fails closed deliberately.

**"No passwords are configured".** `APP_PASSWORD_VIEWER` and
`APP_PASSWORD_EDITOR` are not reaching the container. Check with
`docker compose exec launch-tracker env | grep APP_PASSWORD`.

**Data missing after a redeploy.** The volume mount is wrong — this is the
failure described at the top. Check `docker compose config` and confirm
something is mounted at `/app/data`. Restore from a snapshot afterwards.

**Permission errors writing to the data directory.** With a bind mount, the
host directory must be owned by UID 10001.

**Page loads but is blank or spins.** Usually a reverse proxy not passing
WebSocket upgrade headers. See the nginx block above.

---

## What to hand back

If this deployment is being done by IT rather than the application's author,
the useful things to confirm afterwards are:

1. The URL it is reachable on.
2. Where `/app/data` actually lives on the host or in storage.
3. Whether that location is covered by the existing backup regime, and if not,
   a path that is, so `TRACKER_BACKUP_DIR` can be set.
4. Who to contact if it stops.
