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

## Run it

```
cp .env.example .env          # already done; regenerate secrets if you like
docker compose up --build
```

Then open <http://localhost:8080>. The page reports three things: database
connectivity, service worker registration, and whether you are running in a
browser tab or installed.

To install it, open that URL in Chrome and use the **Install planFC** button, which
appears once Chrome judges the app installable.

## Run the tests

```
docker compose run --rm web python manage.py test
```

## What is here

| Path | Purpose |
|---|---|
| `compose.yaml` | Three services: `db` (Postgres 17), `web` (Django), `caddy` (reverse proxy) |
| `Dockerfile` | The `web` image. Runs gunicorn; Compose overrides it with `runserver` for dev |
| `Caddyfile` | Proxies to Django. Contains the commented production block for planfc.com |
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
  a real host with a real certificate.
- **The Postgres volume is not a backup.** `pgdata` survives `docker compose down`,
  but not `down -v`, and not a dead disk. Before any real payment data exists, we
  need scheduled `pg_dump` output written somewhere off this machine.
- **No authentication yet.** That is the next milestone; `django-allauth` is the
  intended route.
