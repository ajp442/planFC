# Hosting planFC: decision and action plan

**Decision (2026-11-07):** production runs on `corncob`, the dedicated laptop on our
home network, and the public reaches it at `https://planfc.com` through a **named
Cloudflare Tunnel**. A VPS is deferred to keep costs down. We revisit this only if one
of the [triggers in §5](#5-when-to-revisit) happens.

How the stack runs day to day is in [DEPLOYMENT.md](DEPLOYMENT.md). This file
explains why we chose this route and lists the steps to get there.

## Contents

- [1. What we chose and why](#1-what-we-chose-and-why)
- [2. How a request reaches us, and what is encrypted](#2-how-a-request-reaches-us-and-what-is-encrypted)
- [3. Cost](#3-cost)
- [4. Action plan](#4-action-plan)
- [5. When to revisit](#5-when-to-revisit)

---

## 1. What we chose and why

`cloudflared`, a small Cloudflare program, runs beside the stack on corncob. It opens
an **outbound** connection to Cloudflare, and Cloudflare sends visitors to
`planfc.com` down that connection. Compared with the alternatives:

| | Cloudflare Tunnel (chosen) | Port forwarding + dynamic DNS | Small VPS |
|---|---|---|---|
| Monthly cost | $0 | $0 | ~$5–7 |
| Router ports opened | none | 80 and 443 | n/a |
| Home IP changes | don't matter | dynamic DNS updater needed | n/a |
| Works behind ISP CGNAT | yes | no | n/a |
| Who issues the public certificate | Cloudflare, automatically | Caddy (Let's Encrypt) | Caddy (Let's Encrypt) |
| Third party that can read traffic | Cloudflare | none | the VPS provider, in principle |
| Home IP visible to the public | no | yes | n/a |

Other points:

- **Nothing is locked in.** The domain, DNS and app stay the same if we move.
  Moving to a VPS means running the same tunnel there, or pointing DNS at the VPS
  and letting Caddy get its own certificate.
- **Caddy stays.** It's still the reverse proxy in front of Django. With the
  tunnel it serves plain HTTP inside the machine, and Cloudflare handles the
  public HTTPS.

## 2. How a request reaches us, and what is encrypted

```
Phone ──HTTPS──▶ Cloudflare edge ──encrypted tunnel──▶ cloudflared ──HTTP──▶ Caddy ──▶ Django
        (1)            (2)                (3)                 (inside corncob) (4)
```

1. **Phone → Cloudflare: encrypted.** This is ordinary HTTPS, using Cloudflare's
   certificate for `planfc.com`.
2. **Inside Cloudflare's servers: decrypted.** Cloudflare has to read each request
   to route and filter it, so its servers briefly hold the plain contents:
   passwords typed at sign-in, session cookies, member details and ledger pages.
   Card numbers aren't included if payments go to a provider such as Stripe,
   because the phone sends those straight to the provider.
3. **Cloudflare → `cloudflared`: encrypted.** The tunnel itself runs over TLS.
4. **`cloudflared` → Caddy: plain HTTP, but it never leaves corncob.** This hop
   is on Docker's private network on the same machine.

Nothing crosses the internet unencrypted. What we accept is that Cloudflare, a
company that sits in front of about a fifth of all websites, could read our
traffic at step 2. For a club scheduling and payments ledger, we judge that
acceptable. If that changes, §5 says what to do.

## 3. Cost

| Item | Cost |
|---|---|
| `planfc.com` at Cloudflare Registrar (sold at cost, WHOIS privacy included) | about $10–11 per year |
| Cloudflare DNS, Tunnel and the Zero Trust free plan | $0 |
| Public HTTPS certificate | $0 (Cloudflare issues and renews it) |
| Off-site backup storage (Cloudflare R2 or Backblaze B2 free tier) | $0 at our size |
| Electricity for corncob | already being paid |

When buying the domain, decline every add-on the checkout offers. That includes
"SSL certificates", hosting, email and site builders.

## 4. Action plan

Work through these phases in order. Each step ends in something you can check.

### Phase 1: Buy the domain

- [ ] Create a Cloudflare account. Turn on two-factor authentication straight
      away, because whoever controls this account controls the domain.
- [ ] Check that `planfc.com` is available in Cloudflare Registrar. If it isn't,
      agree on another name before continuing.
- [ ] Buy it. Turn on auto-renew. Leave the registrar lock on.
- [ ] Check: the domain appears under *Websites* in the dashboard, using
      Cloudflare's nameservers.

### Phase 2: Code changes (one PR, before production uses the tunnel)

- [ ] **Make Caddy trust the forwarded protocol from the tunnel.** Django decides
      whether a request is HTTPS from `X-Forwarded-Proto`
      (`SECURE_PROXY_SSL_HEADER` in `config/settings.py`). At the moment Caddy
      overwrites that header with `http`, because the tunnel connects to it over
      HTTP. Django would then build `http://` links in confirmation emails and in
      the Google sign-in redirect, and Google sign-in would fail. Add a global
      `servers { trusted_proxies static private_ranges }` block to the inline
      Caddyfile in `compose.yaml`. This also trusts the header from other machines
      on the LAN, which is acceptable for us. A tighter alternative is to trust
      only the Compose network's subnet.
- [ ] **Add a `cloudflared` service to `compose.yaml`** under a Compose profile
      (e.g. `profiles: [tunnel]`), so development stacks don't start it. Pin an
      exact `cloudflare/cloudflared` image version, like the other images. Run it
      with `tunnel --no-autoupdate run`, and read the token from
      `TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}`. Make it depend on `caddy` and
      set `restart: unless-stopped`.
- [ ] **Document the new variables in `.env.example`:** `COMPOSE_PROFILES=tunnel`
      and `CLOUDFLARE_TUNNEL_TOKEN=`.
- [ ] **Check the release version matrix.** `tools/version_matrix.py` lists images
      with `docker compose config --images`, which leaves out services whose
      profile isn't active. Make sure the CI step that runs it enables the `tunnel`
      profile, or that the matrix lists `cloudflared` some other way.
- [ ] Merge the Login system branch first, or at the same time. It adds
      `DJANGO_HTTPS`, which marks cookies Secure once the site is served over HTTPS.
- [ ] Cut a release with these changes.

### Phase 3: Create the tunnel in Cloudflare

- [ ] In the dashboard, open *Zero Trust*. On first use, pick the **Free** plan.
      It may ask for a payment method even though the plan costs nothing.
- [ ] Go to *Networks → Tunnels → Create a tunnel*, choose **Cloudflared**, and
      name it `planfc-corncob`.
- [ ] Copy the tunnel token. Treat it like a password: anyone who has it can serve
      traffic for planfc.com.
- [ ] Add a public hostname: `planfc.com` → service type **HTTP** → URL
      `caddy:80`. The name `caddy` resolves because `cloudflared` runs on the same
      Compose network.
- [ ] Optional: add `www.planfc.com` the same way, or set up a redirect rule from
      `www` to the bare domain.
- [ ] Check: the tunnel shows up in the list. It reports *Inactive* until Phase 4
      starts `cloudflared`.

### Phase 4: Point production at the tunnel

On corncob, in `/srv/planfc`, follow [DEPLOYMENT.md §5.1](DEPLOYMENT.md#51-first-time-setup),
option **C**:

- [ ] Take `compose.yaml` and `.env.example` from the release cut in Phase 2.
- [ ] Set `COMPOSE_PROFILES=tunnel` and `CLOUDFLARE_TUNNEL_TOKEN=<token>`.
- [ ] Add `planfc.com` to `DJANGO_ALLOWED_HOSTS` and `https://planfc.com` to
      `DJANGO_CSRF_TRUSTED_ORIGINS`. Set `DJANGO_HTTPS=1`.
- [ ] Leave `SITE_ADDRESS` at its default `:80` and the host ports at 8080/8443.
      **Don't forward any ports on the router.**
- [ ] `docker compose pull && docker compose up -d`.
- [ ] Check: the tunnel shows *Healthy* in the dashboard, and
      `curl -fsS https://planfc.com/healthz` from any machine reports the expected
      version.

### Phase 5: Cloudflare settings

- [ ] *SSL/TLS → Edge Certificates*: turn on **Always Use HTTPS** and set the
      minimum TLS version to 1.2.
- [ ] *Caching*: confirm that HTML pages and `/sw.js` aren't cached at the edge
      (Cloudflare doesn't cache HTML by default). After a release, if phones still
      get old static files, purge the cache.
- [ ] Wait until the site has run without problems for a while before turning on
      HSTS. Once browsers have cached HSTS, it is hard to undo.

### Phase 6: Prove it works (Foundation done condition)

- [ ] Sign up on a phone. Check that the confirmation link in the email starts with
      `https://planfc.com`. This shows the Phase 2 Caddy fix works.
- [ ] Sign in with Google, once the OAuth client lists
      `https://planfc.com` (see [ACCOUNTS.md](ACCOUNTS.md)).
- [ ] Install the PWA from `https://planfc.com` on a real iPhone and a real Android
      phone.

### Phase 7: What the domain unlocks next

- [ ] **Email:** choose a sending provider (Resend, Postmark or SES). Add its SPF,
      DKIM and DMARC records in Cloudflare DNS, and set the `EMAIL_*` variables.
- [ ] **Off-site backups:** schedule `pg_dump` on corncob, upload to Cloudflare R2
      or Backblaze B2, and **perform one restore**. PLAN.md requires this before
      any real payment data exists. It matters more with home hosting, because the
      ledger otherwise sits on one disk in one house.
- [ ] **Uptime monitoring:** a free external checker (e.g. UptimeRobot) on
      `https://planfc.com/healthz`, so we learn about an outage before members do.

## 5. When to revisit

Stay on the tunnel unless one of these happens:

- **Outages members notice.** Home power or internet failures, or corncob being
  unavailable, cause problems often enough that people complain. Next step: a VPS.
  The same compose stack runs there unchanged.
- **Privacy requirements change.** A payment provider, or the club, requires that
  no third party can read traffic. Next step: a VPS, or port forwarding at home,
  with Caddy holding its own Let's Encrypt certificate (DEPLOYMENT.md §5.1
  option B).
- **Cloudflare changes the terms.** For example, the free tunnel is withdrawn or
  becomes paid.
- **Corncob stops being dedicated.** Someone needs the laptop for something else,
  or it fails.
