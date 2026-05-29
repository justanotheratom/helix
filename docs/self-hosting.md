# Self-hosting Helix on a VM (Hetzner + Cloudflare Tunnel)

This is the battle-tested path for running the **full Helix stack — including
Langfuse + ClickHouse — on a single small VM**, reachable by a team through
Cloudflare Access (SSO) with **no inbound ports open**.

It was validated end-to-end on a **Hetzner CPX31 (4 vCPU / 8 GB / 160 GB,
~$16/mo, Ashburn)**. Any VM with a real Linux kernel works — the only hard
requirement is a real kernel for the worker's overlayfs (so: a VM or bare
metal, **not** a restricted container PaaS like Render/Railway/Cloud Run,
which silently fall back to slow `cp -R`).

```
teammate → https://helix.<yourdomain>
         → Cloudflare Access (SSO / email one-time-PIN; your allowlist)
         → outbound-only tunnel  (VM firewall = SSH only; nothing inbound)
         → caddy:7000 → Helix UI / API / native trace viewer
                         + Langfuse + ClickHouse, all on one box
```

## Why this shape

- **Helix has no built-in auth** (trusted-local by design). On a public box,
  Cloudflare Access is what gates who reaches the UI/API.
- **cloudflared dials out**, so you keep an SSH-only firewall — the auth-less
  app is never exposed on a public port.
- **ClickHouse is the heaviest tenant.** The `docker-compose.prod.yml` overlay
  caps it (and the Node services) so the whole stack fits ~8 GB.

---

## 0. Prerequisites

- A **Hetzner Cloud** account + project (billing). VM is ~$16/mo for CPX31.
- A **Cloudflare** account + a **domain on Cloudflare** (nameservers pointed at
  CF; ~$10/yr at Cloudflare Registrar if you need one). Zero Trust **Free**
  plan covers Access for up to 50 users.
- LLM **provider API keys** for whatever models your compiles use
  (OpenAI / Gemini / Anthropic / …).
- Local tools: `ssh`, and optionally the [`hcloud`](https://github.com/hetznercloud/cli)
  CLI (`brew install hcloud`) if you provision from the terminal.

---

## 1. Provision the VM

Either create a **CPX31 / Ubuntu 24.04 / Ashburn (`ash`)** in the Hetzner
Console and paste your SSH public key, or via `hcloud`:

```bash
# one-time auth (stores the token locally; never paste it elsewhere)
hcloud context create helix          # paste a Read&Write API token at the prompt

# dedicated key (or reuse your own)
ssh-keygen -t ed25519 -f ~/.ssh/helix_hetzner -N "" -C helix
hcloud ssh-key create --name helix --public-key-from-file ~/.ssh/helix_hetzner.pub

# firewall: inbound SSH only (outbound is unrestricted — cloudflared needs it)
hcloud firewall create --name helix-fw
hcloud firewall add-rule helix-fw --direction in --protocol tcp --port 22 \
  --source-ips 0.0.0.0/0 --source-ips ::/0 --description SSH

# the server
hcloud server create --name helix --type cpx31 --image ubuntu-24.04 \
  --location ash --ssh-key helix --firewall helix-fw
```

Note the IPv4 it prints. SSH in with `ssh -i ~/.ssh/helix_hetzner root@<IP>`.

---

## 2. Base server setup

```bash
ssh -i ~/.ssh/helix_hetzner root@<IP> 'bash -s' <<'EOF'
set -e
# 4 GB swap (safety net on an 8 GB box; ClickHouse + a compile can spike)
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
sysctl -qw vm.swappiness=10; echo "vm.swappiness=10" > /etc/sysctl.d/99-helix.conf
# Docker + git
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
apt-get install -y -q git
EOF
```

---

## 3. Clone Helix + generate the production `.env`

```bash
ssh -i ~/.ssh/helix_hetzner root@<IP> 'git clone --depth 1 https://github.com/justanotheratom/helix /opt/helix'
```

Generate `.env` with strong secrets **on the server** (so they never leave the
box). Run this on the server (`ssh … 'bash -s'`):

```bash
cd /opt/helix/deploy && umask 077
cat > .env <<EOF
LANGFUSE_SAMPLE_RATE=1.0
HELIX_HOST_PORT=7000
HELIX_WORKER_REPLICAS=1

HELIX_POSTGRES_PASSWORD=$(openssl rand -hex 24)
HELIX_MINIO_ROOT_USER=helix
HELIX_MINIO_ROOT_PASSWORD=$(openssl rand -hex 24)
HELIX_REDIS_PASSWORD=$(openssl rand -hex 24)

LANGFUSE_POSTGRES_PASSWORD=$(openssl rand -hex 24)
LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 24)
LANGFUSE_MINIO_ROOT_USER=langfuse
LANGFUSE_MINIO_ROOT_PASSWORD=$(openssl rand -hex 24)
LANGFUSE_REDIS_PASSWORD=$(openssl rand -hex 24)
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)

LANGFUSE_INIT_ORG_ID=helix
LANGFUSE_INIT_ORG_NAME=helix
LANGFUSE_INIT_PROJECT_ID=helix
LANGFUSE_INIT_PROJECT_NAME=helix
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-$(openssl rand -hex 16)
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-$(openssl rand -hex 16)
LANGFUSE_INIT_USER_EMAIL=you@example.com
LANGFUSE_INIT_USER_NAME=owner
LANGFUSE_INIT_USER_PASSWORD=$(openssl rand -hex 16)
EOF
chmod 600 .env
```

Then append your **provider keys** (only the ones you use). From your laptop,
without printing them:

```bash
grep -E '^(OPENAI_API_KEY|GEMINI_API_KEY|ANTHROPIC_API_KEY)=..*' ~/path/to/local/.env \
  | ssh -i ~/.ssh/helix_hetzner root@<IP> 'cat >> /opt/helix/deploy/.env'
```

---

## 4. Build + bring up the stack (with the small-host overlay)

The `docker-compose.prod.yml` overlay is what makes the full stack fit ~8 GB:
it caps ClickHouse (`clickhouse-lowmem.xml`, 3 GiB), and sizes the Langfuse
Node services so they don't OOM their own V8 heap. **Always include it.**

```bash
ssh -i ~/.ssh/helix_hetzner root@<IP> 'set -e
cd /opt/helix && bash deploy/build.sh        # stage build context
cd deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env up -d'
```

First boot takes a few minutes (image pulls + Langfuse migrations). Verify:

```bash
ssh -i ~/.ssh/helix_hetzner root@<IP> '
cd /opt/helix/deploy
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -s -o /dev/null -w "UI %{http_code}\n"  http://localhost:7000/
curl -s -o /dev/null -w "API %{http_code}\n" http://localhost:7000/api/jobs
free -h | grep -E "Mem|Swap"'
```

You want all containers healthy, UI+API `200`, and a couple GB of memory free.
At this point the stack runs but is only reachable on the box's `localhost`
(firewall = SSH only) — do **not** expose port 7000; the tunnel handles access.

> **Gotchas this overlay already fixes** (learned the hard way on 8 GB):
> - ClickHouse otherwise sizes caches to host RAM and starves everything.
> - `langfuse-web`/`-worker` are Node; too-tight a `mem_limit` makes Node cap
>   its V8 heap below what it needs → "Reached heap limit" crash loop.
> - Recent `langfuse:3` binds to the container hostname, so its loopback
>   healthcheck fails → we set `HOSTNAME=0.0.0.0`.

---

## 5. Cloudflare Tunnel + Access (team access, no inbound)

This exposes the UI to your team behind SSO, with zero inbound ports.

### 5a. Enable Zero Trust (one-time, dashboard — **cannot** be done via API)

At [one.dash.cloudflare.com](https://one.dash.cloudflare.com): pick a **team
name** and select the **Free** plan. (It may ask for a card to finish signup;
Free isn't charged.) This is the only mandatory manual click.

### 5b. Create the tunnel + DNS + Access (API or dashboard)

**Dashboard:** Zero Trust → Networks → Tunnels → create `helix` (connector
*Cloudflared*) → copy its **token**. Public Hostname tab: `helix.<yourdomain>`
→ Service **HTTP** → URL **`caddy:7000`**. Then Access → Applications → add a
**self-hosted** app on that hostname with an **Allow** policy listing your
team's emails (email one-time-PIN needs no IdP setup).

**API** (with a token scoped *Cloudflare Tunnel:Edit*, *Access Apps &
Policies:Edit*, *DNS:Edit*, *Zone:Read*) — after 5a is done:
- `POST /accounts/{acct}/cfd_tunnel` `{"name":"helix","config_src":"cloudflare"}`
- `GET  /accounts/{acct}/cfd_tunnel/{id}/token` → the tunnel token
- `PUT  /accounts/{acct}/cfd_tunnel/{id}/configurations`
  `{"config":{"ingress":[{"hostname":"helix.<yourdomain>","service":"http://caddy:7000"},{"service":"http_status:404"}]}}`
- `POST /zones/{zone}/dns_records`
  `{"type":"CNAME","name":"helix","content":"{id}.cfargotunnel.com","proxied":true}`
- `POST /accounts/{acct}/access/apps`
  `{"name":"Helix","domain":"helix.<yourdomain>","type":"self_hosted","session_duration":"24h"}`
- `POST /accounts/{acct}/access/apps/{app}/policies`
  `{"name":"team","decision":"allow","include":[{"email":{"email":"a@x.com"}}, …]}`

### 5c. Run the tunnel

Put the tunnel token in the server `.env` and start `cloudflared` (the
`docker-compose.cloudflare.yml` overlay):

```bash
ssh -i ~/.ssh/helix_hetzner root@<IP> '
cd /opt/helix/deploy
echo "CF_TUNNEL_TOKEN=<tunnel-token>" >> .env && chmod 600 .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloudflare.yml \
  --env-file .env up -d cloudflared'
```

### 5d. Verify the gate

```bash
curl -sI https://helix.<yourdomain>/ | grep -iE "^HTTP|^location"
```

Expect `HTTP/2 302` → `…cloudflareaccess.com/…/login` (the SSO gate), **not**
the Helix UI. Then in a browser, an allowed email gets a one-time code and
reaches the UI; a non-allowed email is blocked.

### 5e. CLI / programmatic access (service token)

Browser users pass Access via SSO, but the `helix` **CLI** (and any script)
isn't a browser — it would hit the same 302 gate. To let it through
non-interactively, create a Cloudflare Access **service token** and a
**Service Auth** policy on the Helix app; the CLI then sends two headers that
Access validates at the edge. (The CLI already does this automatically when
`CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` are set — it's a no-op
locally.)

**Create the token + policy** (API token needs *Access: Service Tokens · Edit*
in addition to the earlier scopes; or do both in the dashboard under
Access → Service Auth):

```
# create the token — the client_secret is returned ONLY here, capture it
POST /accounts/{acct}/access/service_tokens   {"name":"helix-cli"}
  -> result: { id, client_id, client_secret }

# allow that token on the Helix app (coexists with the human email policy)
POST /accounts/{acct}/access/apps/{app}/policies
  {"name":"helix-cli-svc","decision":"non_identity",
   "include":[{"service_token":{"token_id":"<id>"}}]}
```

(Dashboard equivalent: Access → Service Auth → Create Service Token; then on
the Helix application add a policy with action **Service Auth** including that
token.)

**Use it** — from a consumer worktree (the one with `.helix.toml`), point the
CLI at the remote and supply the token:

```bash
export HELIX_HOME=~/GitHub/helix
export HELIX_BASE_URL=https://helix.<yourdomain>
export CF_ACCESS_CLIENT_ID=<client_id>
export CF_ACCESS_CLIENT_SECRET=<client_secret>

uv run --project "$HELIX_HOME" helix list
uv run --project "$HELIX_HOME" helix submit compile <base>/<overlay>/<p>/<v>/compile.config.NNNN.yaml
uv run --project "$HELIX_HOME" helix status <job-id>   # logs / export ...
```

`submit` uploads the snapshot + overlay bundle to the **remote** MinIO and the
**remote** worker runs the job (traced to the remote Langfuse) — i.e. you're
driving the shared box, not your laptop. Verify quickly:

```bash
# no token -> 302 (blocked); with token -> 200
curl -s -o /dev/null -w "%{http_code}\n" https://helix.<yourdomain>/api/jobs
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://helix.<yourdomain>/api/jobs
```

> **The service token is a shared credential** — anyone holding the
> ID/secret can submit jobs to the remote (spending your LLM keys). Store it
> in a secret manager / `.env`, never in scripts or chat. Rotate via
> `POST …/service_tokens/{id}/rotate` (or the dashboard) if it leaks. For
> stronger per-user CLI auth, use `cloudflared access` browser-login instead
> of a shared token.

---

## 6. Day-to-day ops

**Canonical bring-up** (all three overlays, so `cloudflared` stays managed):

```bash
cd /opt/helix/deploy && docker compose \
  -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloudflare.yml \
  --env-file .env up -d
```

Everything is `restart: unless-stopped`, so a reboot restores the full stack +
tunnel automatically.

- **Update Helix:** `cd /opt/helix && git pull && bash deploy/build.sh` then the
  bring-up command above.
- **Add/remove teammates:** edit the Access policy (dashboard or API). For the
  full teammate onboarding flow (browser + CLI), see
  [team-access.md](team-access.md).
- **Reclaim storage:** snapshots + venvs + blobs grow; run `helix gc --apply`
  (or `POST /api/gc?dry_run=false`) periodically.
- **Submitting jobs:** teammates use the *UI* on the shared box; for
  programmatic / CLI submits against the remote, set up a service token — see
  [§5e](#5e-cli--programmatic-access-service-token).

## Sizing

| Stack | RAM floor |
|---|---|
| Full (incl. Langfuse + ClickHouse) | **~8 GB** (CPX31). Observed ~2.5 GB used at idle; ClickHouse capped at 3 GiB. |

ClickHouse is the reason for 8 GB. On a bigger box, raise
`max_server_memory_usage` in `clickhouse-lowmem.xml` (or drop the prod
overlay's caps entirely).
