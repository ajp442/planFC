# planFC

Pickup game planning for our football club. See [`PLAN.md`](PLAN.md) for scope and milestones.

This repository currently holds the **Foundation proof of concept**: a Django app
behind Caddy with Postgres, installable as a PWA, running under Docker Compose.

## Prerequisites

Docker Engine is already installed. You also need Compose v2 — the `docker-compose`
v1 on this machine is the retired Python implementation and does not understand
this `compose.yaml`:

```
sudo apt install docker-compose-v2
```

That gives you `docker compose` (a space, not a hyphen).

## Run it from a clone (development)

```
cp .env.example .env          # already done; regenerate secrets if you like
docker compose up --build
```

`compose.override.yaml` is merged in automatically: it builds from source,
bind-mounts the tree and runs `runserver` with `DEBUG` on. If your uid is not
1000 (`id -u`), set `APP_UID` in `.env` or the container cannot write into the tree.

Then open <http://localhost:8080>. The page reports three things: database
connectivity, service worker registration, and whether you are running in a
browser tab or installed.

To install it, open that URL in Chrome and use the **Install planFC** button, which
appears once Chrome judges the app installable.

## Run it without a clone

Each version tag (`git tag v0.1.0 && git push origin v0.1.0`) whose tests pass publishes the image
to `ghcr.io/ajp442/planfc` for amd64 and arm64. Anyone can then run:

```
curl -O https://raw.githubusercontent.com/ajp442/planFC/main/compose.yaml
curl -o .env https://raw.githubusercontent.com/ajp442/planFC/main/.env.example
# edit .env: real DJANGO_SECRET_KEY and POSTGRES_PASSWORD, your hostnames
docker compose up -d
```

That runs gunicorn with `DEBUG` off. To upgrade: `docker compose pull && docker compose up -d`.
GHCR makes a new package private, so after the first publish set its visibility to
public under the package settings on GitHub.

## Run the tests

```
docker compose run --rm web python manage.py test
```

The browser tests drive the running stack in emulated phones: a Pixel 7 on
Chromium (Android Chrome's engine) and an iPhone 15 on WebKit (iOS Safari's). With
`docker compose up` running:

```
./e2e/run.sh                  # both devices
./e2e/run.sh --project ios    # one device
```

This needs only Docker, because the browsers come in Microsoft's Playwright image.
Emulation checks the service worker, manifest, icons and offline cache under both
engines. It can't check installing or standalone mode, so try those on a real
phone before a release.

CI (`.github/workflows/ci.yml`) runs both suites against the built image on every
pull request and push to `main`. A version tag publishes the image only if they pass.

## What is here

| Path | Purpose |
|---|---|
| `compose.yaml` | The whole deployment: `db` (Postgres 17), `web` (the published image), `caddy` (reverse proxy, config inline) |
| `compose.override.yaml` | Dev overlay: build from source, bind mount, `runserver` |
| `Dockerfile` | The `web` image. Migrates, then runs gunicorn; static files baked in |
| `.github/workflows/ci.yml` | Tests the built image; pushes it on version tags once tests pass |
| `e2e/` | Playwright browser tests in emulated Android and iOS devices |
| `config/` | Django settings, URLs, WSGI entrypoint |
| `core/` | The hello-world view, health check, PWA templates, tests |
| `static/` | Stylesheet, install-prompt JavaScript, placeholder icons |
| `tools/make_icons.py` | Regenerates the placeholder icons; delete once we have a real crest |

## Notes and known gaps

- **The icons are placeholders.** Green squares reading "FC". Replace the PNGs in
  `static/icons/` with a real crest.
- **Testing install on a phone needs HTTPS.** Browsers grant `http://localhost` a
  secure context, so desktop Chrome installs fine, but a phone reaching this laptop
  over the LAN gets plain HTTP and will refuse to register the service worker.
  Options: a Cloudflare Tunnel, Tailscale, or waiting until planfc.com resolves to
  a real host with a real certificate. For the latter, set `SITE_ADDRESS=planfc.com`,
  `HTTP_PORT=80` and `HTTPS_PORT=443` in `.env`; Caddy handles the certificate.
- **The Postgres volume is not a backup.** `pgdata` survives `docker compose down`,
  but not `down -v`, and not a dead disk. Before any real payment data exists, we
  need scheduled `pg_dump` output written somewhere off this machine.
- **No authentication yet.** That is the next milestone; `django-allauth` is the
  intended route.
