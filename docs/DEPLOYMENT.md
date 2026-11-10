# Running planFC: development and production

This explains how to start a **development** instance and a **production** instance
of planFC, and how to run both at once on the dedicated laptop, `corncob`. For why
the Compose files are shaped this way, see
[ARCHITECTURE.md §5](ARCHITECTURE.md#5-containers-and-deployment). For why
production is on this laptop behind a Cloudflare Tunnel, and the steps to set
that up, see [HOSTING.md](HOSTING.md).

## Contents

- [1. The two instances at a glance](#1-the-two-instances-at-a-glance)
- [2. What keeps them apart](#2-what-keeps-them-apart)
- [3. Prerequisites on corncob](#3-prerequisites-on-corncob)
- [4. Development instance](#4-development-instance)
- [5. Production instance](#5-production-instance)
- [6. One-time switch from the old single stack](#6-one-time-switch-from-the-old-single-stack)
- [7. Day-to-day cheat sheet](#7-day-to-day-cheat-sheet)
- [8. Known gaps](#8-known-gaps)

---

## 1. The two instances at a glance

| | Development | Production |
|---|---|---|
| Lives in | the git clone, `~/repos/planFC` | `/srv/planfc`, which holds only `compose.yaml` and `.env` |
| Compose files | `compose.yaml` + `compose.override.yaml` (merged automatically) | `compose.yaml` alone |
| Compose project | `planfc-dev-<you>` on corncob (`planfc-dev` if unset) | `planfc` |
| Containers | `planfc-dev-<you>-{db,web,caddy}-1` | `planfc-{db,web,caddy}-1` |
| Database volume | `planfc-dev-<you>_pgdata` | `planfc_pgdata` |
| `web` image | `planfc-dev-<you>-web`, built from your working tree | `ghcr.io/ajp442/planfc:<version>`, published by CI |
| Server | `runserver`, reloads on save, `DEBUG` on | gunicorn with 3 workers, `DEBUG` off |
| Source | bind-mounted from the clone | baked into the image |
| URL on corncob | zjp: <http://localhost:8081>, ajp: <http://localhost:8082> (see §4) | <http://localhost:8080>; later <https://myplanfc.com> |
| Starts at boot | yes, if it was running when the machine went down | yes (`restart: unless-stopped`) |
| Looks like | amber "FC DEV" icon, named **planFC Dev**, a Development badge on the page | green "FC" icon, named **planFC** |
| Version shown | `dev` | the release, e.g. `0.1.3 (a1b2c3d)` |

## 2. What keeps them apart

Both instances run the same three services, `db`, `web` and `caddy`, on one Docker
daemon. A fourth, `cloudflared`, starts only in stacks whose `.env` sets
`COMPOSE_PROFILES=tunnel`. Each of those stacks has its own Cloudflare Tunnel
([HOSTING.md](HOSTING.md)). Five things keep them from interfering:

1. **Separate Compose project names.** `compose.yaml` sets `name: planfc`, and
   `compose.override.yaml` overrides it with `name: planfc-dev`. Docker derives
   container, network and volume names from the project, so each instance gets its
   own database volume. Running `docker compose down -v` in the clone deletes only
   the dev database.
2. **Separate directories.** Compose merges `compose.override.yaml` only when it
   sits next to `compose.yaml`. Production lives outside the clone, so it can't
   pick up the dev overlay by accident, and each directory reads its own `.env`.
3. **Separate host ports.** On corncob, production uses the defaults, 8080 and
   8443, because Tailscale Serve already holds port 80 for the writing group site.
   The tunnel reaches Caddy inside Docker, so serving myplanfc.com doesn't need
   ports 80 and 443 on the host (they would only matter for option B in §5.1).
   Each dev stack sets
   its own ports in its clone's `.env` (see the port table in §4).
4. **Different looks.** `compose.override.yaml` sets `PLANFC_ENVIRONMENT=development`,
   which swaps in the amber icons from `static/icons/dev/`, renames the app to
   planFC Dev and adds a Development badge. An installed app has no address bar, so
   the icon and name are what tell the two apart on a phone. The published image
   defaults to production.
5. **Separate images.** Dev builds and tags `<project>-web`, such as `planfc-dev-zjp-web`. Production pulls a
   pinned release from GHCR, so a dev build never ends up in production.

> **Rule of thumb:** a `docker compose` command acts on whichever instance's
> directory you run it from. Check `pwd` before running anything destructive, and
> never run `down -v` in `/srv/planfc`.

## 3. Prerequisites on corncob

These are already in place on corncob. Check them again after reinstalling the OS.

| Requirement | Check | Fix |
|---|---|---|
| Docker Engine, started at boot | `systemctl is-enabled docker` prints `enabled` | `sudo systemctl enable --now docker` |
| Compose v2.23 or later (`docker compose`, with a space) | `docker compose version` | `sudo apt install docker-compose-v2` |
| Your user can talk to Docker | `docker ps` works without `sudo` | `sudo usermod -aG docker $USER`, then log in again |
| Closing the lid doesn't suspend the laptop | `/etc/systemd/logind.conf.d/lid.conf` sets `HandleLidSwitch*=ignore` | Create that file, then `sudo systemctl restart systemd-logind` |

A production instance also needs the laptop to stay on AC power and on the network.

## 4. Development instance

Use this to change code and see the result straight away.

### First run

```sh
cd ~/repos/planFC
cp .env.example .env
# Edit .env and replace both secrets. Any values will do in dev:
#   python3 -c "import secrets; print(secrets.token_urlsafe(50))"
id -u    # if this isn't 1000, add APP_UID=<that number> to .env
# On corncob, also set your project name and ports (see "Dev stacks on corncob").
docker compose up --build
```

Open your dev URL, such as <http://localhost:8081>. The page should report the
database as connected and the service worker as registered.

### Everyday use

| Task | Command (from `~/repos/planFC`) |
|---|---|
| Start in the background | `docker compose up -d --build` |
| Follow logs | `docker compose logs -f web` |
| Stop, keeping the data | `docker compose down` |
| Wipe the dev database and start fresh | `docker compose down -v` (affects dev only, because of §2) |
| Django shell or management command | `docker compose exec web python manage.py <command>` |
| Create an admin login | `docker compose exec web python manage.py createsuperuser` |
| Unit tests | `docker compose run --rm web python manage.py test` |
| Browser tests (stack must be up) | `./e2e/run.sh` |
| Test the production image locally, as CI does | see "Testing the shipped image" below |

Python code reloads on save. Changing `requirements.txt` or the `Dockerfile` needs
`--build` again.

### Dev stacks on corncob

Production already uses the default ports, 8080 and 8443, so on corncob a dev
stack must not run on the defaults. Each person runs their own dev stack from
their own clone, with its own project name and ports:

| Stack | Project | HTTP | HTTPS |
|---|---|---|---|
| Production | `planfc` | 8080 | 8443 |
| zjp's dev | `planfc-dev-zjp` | 8081 | 8444 |
| ajp's dev | `planfc-dev-ajp` | 8082 | 8445 |

Set them in that clone's `.env`. For example, zjp's:

```ini
COMPOSE_PROJECT_NAME=planfc-dev-zjp
HTTP_PORT=8081
HTTPS_PORT=8444
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8081,https://*.trycloudflare.com
```

`COMPOSE_PROJECT_NAME` overrides the `name:` in `compose.override.yaml`, so the
stack gets its own containers, database volume and image (`planfc-dev-zjp-web`).
Every `docker compose` command in that clone then acts on it alone. A new person
takes the next free ports (8083 and 8446) and adds a row to this table.

### Testing on a phone

Phones need HTTPS before they will register the service worker. For a permanent
address, give the stack its own subdomain and tunnel, such as
`zjp-dev.myplanfc.com` ([HOSTING.md Phase 8](HOSTING.md#phase-8-dev-stacks-on-subdomains-optional)).
For a one-off test, a Cloudflare quick tunnel gives a random HTTPS address with no
setup in the dashboard. `cloudflared` isn't installed on corncob itself; install
it from Cloudflare's apt repository, then run:

```sh
cloudflared tunnel --url http://localhost:8081    # your dev stack's HTTP port
```

`.env.example` already allows `*.trycloudflare.com`, so the random URL that
`cloudflared` prints works without further edits.

### Testing the shipped image

To run the same image production will run, without touching production, build it
and start it with `compose.yaml` alone under a throwaway project name and other ports:

```sh
docker build -t ghcr.io/ajp442/planfc:local .
PLANFC_VERSION=local HTTP_PORT=8090 HTTPS_PORT=8453 \
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8090 \
  docker compose -p planfc-imgtest -f compose.yaml up -d
BASE_URL=http://localhost:8090 ./e2e/run.sh
docker compose -p planfc-imgtest -f compose.yaml down -v
```

The project name has to be given with `-p`: with `-f compose.yaml` alone, Compose
would otherwise use `planfc`, which is production.

## 5. Production instance

Production runs a published, tested release and never runs source from the clone.
Every version tag that passes CI is pushed to `ghcr.io/ajp442/planfc`; see
[ARCHITECTURE.md §5.5](ARCHITECTURE.md#55-ci-and-release-pipeline-githubworkflowsciyml).

### 5.1 First-time setup

Pick the release to run. The list is at
<https://github.com/ajp442/planFC/releases>, and this example uses `0.1.1`. Take
`compose.yaml` from **that tag**, not from `main`, so the file matches the image:

```sh
sudo install -d -o "$USER" -g "$USER" /srv/planfc
cd /srv/planfc
VERSION=0.1.1
curl -fsSLo compose.yaml "https://raw.githubusercontent.com/ajp442/planFC/v$VERSION/compose.yaml"
curl -fsSLo .env         "https://raw.githubusercontent.com/ajp442/planFC/v$VERSION/.env.example"
chmod 600 .env
```

Edit `/srv/planfc/.env`. Generate **new** secrets, and don't copy them from dev:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # run once per secret
```

Choose the block below that matches how production is reached.

**A. On the LAN or through a tunnel only** (until the domain is set up). Ports
8080 and 8443, because Tailscale Serve holds port 80 on corncob:

```ini
DJANGO_SECRET_KEY=<new random value>
POSTGRES_PASSWORD=<new random value>
PLANFC_VERSION=0.1.1

HTTP_PORT=8080
HTTPS_PORT=8443
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,corncob,corncob.tail1d2df3.ts.net,.trycloudflare.com
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://corncob:8080,http://corncob.tail1d2df3.ts.net:8080,https://*.trycloudflare.com
```

**C. myplanfc.com through the Cloudflare Tunnel (the chosen route).** Needs a
release that includes the `cloudflared` service
([HOSTING.md Phase 2](HOSTING.md#phase-2-code-changes-one-pr-before-production-uses-the-tunnel)),
and the token of the `planfc-prod` tunnel from Phase 3. Don't forward any router
ports. Caddy stays on plain HTTP, and Cloudflare provides the certificate:

```ini
DJANGO_SECRET_KEY=<new random value>
POSTGRES_PASSWORD=<new random value>
PLANFC_VERSION=<the release with the tunnel service>

COMPOSE_PROFILES=tunnel
CLOUDFLARE_TUNNEL_TOKEN=<token from the Cloudflare dashboard>
HTTP_PORT=8080
HTTPS_PORT=8443
DJANGO_ALLOWED_HOSTS=myplanfc.com,localhost,127.0.0.1,corncob,corncob.tail1d2df3.ts.net
DJANGO_CSRF_TRUSTED_ORIGINS=https://myplanfc.com,http://localhost:8080,http://corncob:8080,http://corncob.tail1d2df3.ts.net:8080
DJANGO_HTTPS=1
```

`DJANGO_HTTPS=1` makes the session cookie Secure, so signing in only works over
`https://myplanfc.com`. The LAN addresses still serve pages, but they can't be used
to sign in.

**B. Serving myplanfc.com directly** (the fallback if we leave Cloudflare; see
[HOSTING.md §5](HOSTING.md#5-when-to-revisit)). The domain's DNS must point at
this network's public IP, and the router must forward TCP 80 and 443 to corncob.
Caddy then obtains the certificate by itself:

```ini
DJANGO_SECRET_KEY=<new random value>
POSTGRES_PASSWORD=<new random value>
PLANFC_VERSION=0.1.1

SITE_ADDRESS=myplanfc.com
HTTP_PORT=80
HTTPS_PORT=443
DJANGO_ALLOWED_HOSTS=myplanfc.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://myplanfc.com
```

Then start it:

```sh
cd /srv/planfc
docker compose pull
docker compose up -d
docker compose ps                       # all three should be Up, db (healthy)
curl -fsS http://localhost/healthz      # use https://myplanfc.com/healthz in options B and C
docker compose exec web python manage.py createsuperuser
```

`restart: unless-stopped` and Docker starting at boot bring production back after
a reboot or power cut. Don't touch it after that.

To check production in emulated phones, run this from the clone. It only reads,
and does no harm:

```sh
cd ~/repos/planFC && BASE_URL=http://localhost ./e2e/run.sh
```

### 5.2 Upgrading to a new release

```sh
cd /srv/planfc
# 1. Back up first: migrations run on start and are not undone by rolling back.
mkdir -p ~/planfc-backups
docker compose exec -T db pg_dump -U planfc -Fc planfc > ~/planfc-backups/planfc-$(date +%F-%H%M).dump
# 2. Take the new release's compose.yaml, and diff .env.example for new variables.
VERSION=0.1.2
curl -fsSLo compose.yaml "https://raw.githubusercontent.com/ajp442/planFC/v$VERSION/compose.yaml"
curl -fsSL "https://raw.githubusercontent.com/ajp442/planFC/v$VERSION/.env.example" | diff - .env
# 3. Set PLANFC_VERSION=$VERSION in .env, then:
docker compose pull
docker compose up -d
curl -fsS http://localhost/healthz      # "version" should now say $VERSION
```

The page footer shows the same version and commit, for checking from a phone.

Read the release notes before upgrading. A release that changes the Postgres major
version needs a manual dump and restore, as described in
[ARCHITECTURE.md §5.2](ARCHITECTURE.md#52-compose-one-file-for-deployers-an-overlay-for-developers).

### 5.3 Rolling back

Put the previous `compose.yaml` and `PLANFC_VERSION` back, then run
`docker compose up -d`. If the bad release ran a migration, the old code may not
work with the new schema. In that case restore the dump you took in step 1:

```sh
cd /srv/planfc
docker compose stop web
docker compose exec -T db pg_restore -U planfc -d planfc --clean --if-exists < ~/planfc-backups/<file>.dump
docker compose up -d
```

### 5.4 Things never to do in `/srv/planfc`

- `docker compose down -v`, `docker volume rm planfc_pgdata`, or
  `docker system prune --volumes`. Each of these deletes the ledger.
- Copying `compose.override.yaml` in. That would turn production into a dev build.
- Using `PLANFC_VERSION=latest`. Pin a version, so a reboot or a stray `pull` can't
  upgrade production without anyone deciding to.

## 6. One-time switch from the old single stack

Before `compose.override.yaml` named the dev project, a clone ran as project
`planfc`, the name production now uses. On corncob that stack has been running
from `~/repos/planFC` since September, and its volumes (`planfc_pgdata`,
`planfc_caddy_data`, `planfc_caddy_config`) hold proof-of-concept data only. Do
this once, before starting production:

```sh
cd ~/repos/planFC
git pull                                  # picks up name: planfc-dev
# Optional: keep a copy of the old dev database.
docker compose -p planfc exec -T db pg_dump -U planfc -Fc planfc > ~/planfc-old-dev.dump
# Stop the old stack. -p is needed because the override now says planfc-dev.
docker compose -p planfc down
# Remove its volumes, so production starts on an empty database with its own
# password. Postgres ignores POSTGRES_PASSWORD on a volume that already exists.
docker volume rm planfc_pgdata planfc_caddy_data planfc_caddy_config
# Start dev under its new name. It gets a fresh planfc-dev_pgdata.
docker compose up -d --build
```

Then follow [§5.1](#51-first-time-setup).

If you keep the old volumes instead, production will adopt the dev data, and
`POSTGRES_PASSWORD` in `/srv/planfc/.env` must match the old dev password.

## 7. Day-to-day cheat sheet

```sh
# What's running, for both instances
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'

# Development
cd ~/repos/planFC && docker compose up -d --build    # → http://localhost:8081 (zjp)
cd ~/repos/planFC && docker compose logs -f web
cd ~/repos/planFC && docker compose down

# Production
cd /srv/planfc && docker compose ps                  # → http://localhost:8080
cd /srv/planfc && docker compose logs -f --since 1h
cd /srv/planfc && docker compose restart web
```

## 8. Known gaps

- **Backups don't exist yet.** The `pg_dump` in §5.2 runs by hand and writes to the
  same disk. Before any real payment data exists, PLAN.md requires scheduled dumps
  written off this machine, and a restore that has actually been tested.
- **The tunnel needs a release.** Option C needs a published release that
  includes the `cloudflared` service. Until one is cut, production can only be
  reached on the LAN (option A).
- **HTTPS security settings** (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS)
  aren't turned on yet. See [ARCHITECTURE.md §7](ARCHITECTURE.md#7-known-gaps-and-things-to-watch).
- **The laptop is a single point of failure.** One disk, one house, one power
  supply. We accepted this to avoid VPS costs (see [HOSTING.md](HOSTING.md)), so
  off-site backups and uptime monitoring are required. If outages become
  something members notice, the process above transfers to a VPS unchanged; only
  the directory's host changes.
