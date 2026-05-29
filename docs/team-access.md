# Onboarding teammates to a shared Helix

This is for a team sharing **one** Helix instance — the stack runs on a single
box (see [self-hosting.md](self-hosting.md)) behind Cloudflare Access, and
teammates connect to it. Teammates do **not** run their own stack.

There are two tiers. Most people only need Tier 1.

```
teammate → https://helix.<yourdomain>
         → Cloudflare Access (SSO / email one-time-PIN; the allowlist)
         → the shared Helix (UI + API + traces) on the box
```

---

## Tier 1 — Use the UI (view jobs, progress, traces): zero setup

If the teammate's email is on the Access allowlist, they just:

1. Open **`https://helix.<yourdomain>`**
2. Cloudflare prompts for their email → **Send me a code** → enter the code
   from their inbox
3. They're in — full UI: job list, live GEPA/eval progress, trace viewer.

Nothing to install. This is all most teammates need.

### Admin: add/remove an allowlisted email

**Dashboard:** Zero Trust → Access → Applications → *Helix* → the policy →
edit the **Include → Emails** list.

**API** (token scoped *Access: Apps and Policies · Edit*):

```bash
ACCT=<account-id>; APP=<helix-app-id>; POL=<policy-id>
curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCT/access/apps/$APP/policies/$POL" \
  -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"helix-team","decision":"allow","include":[
        {"email":{"email":"a@yourco.com"}},
        {"email":{"email":"b@yourco.com"}}]}'
```

(The `include` list is the full allowlist — list every allowed email each time.)
You can also allow a whole domain with `{"email_domain":{"domain":"yourco.com"}}`.

---

## Tier 2 — Submit jobs from their own machine (CLI)

Needed only if a teammate runs `helix submit` / `list` / `logs` / `export`
from their laptop against the shared box. The stack stays remote — **no Docker
on the teammate's machine.** They need `uv`, `git`, a clone of the **consumer
repo** (the one with `.helix.toml` — `helix submit` snapshots *their* checkout),
and a clone of Helix, plus a Cloudflare Access **service token**.

```bash
# one-time
curl -LsSf https://astral.sh/uv/install.sh | sh          # if uv isn't installed
git clone https://github.com/justanotheratom/helix ~/GitHub/helix
# (they already have the consumer repo checked out)

# env — add to ~/.zshrc (or a sourced secrets file)
export HELIX_HOME=~/GitHub/helix
export HELIX_BASE_URL=https://helix.<yourdomain>
export CF_ACCESS_CLIENT_ID=<their-service-token-client-id>
export CF_ACCESS_CLIENT_SECRET=<their-service-token-client-secret>
alias helix='uv run --project $HELIX_HOME helix'

# use it, from inside the consumer repo
cd ~/path/to/<consumer-repo>            # has .helix.toml
helix list
helix submit compile <base>/<overlay>/<p>/<v>/compile.config.NNNN.yaml
helix status <job-id>     # logs / export …
```

`submit` publishes a content-addressed snapshot of the teammate's committed
base tree + their overlay-root edits to the **remote** MinIO, and the **remote**
worker runs the job. So everyone's submits land on the same shared box.

> The CLI sends the `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers
> automatically when those env vars are set (and no-ops them when unset, i.e.
> for local use). See [self-hosting.md §5e](self-hosting.md#5e-cli--programmatic-access-service-token)
> for how the service token + Service Auth policy are created.

### Admin: per-teammate service tokens (recommended)

Prefer **one service token per teammate** over a single shared one — you can
revoke/audit individually. Mint via API (token scoped *Access: Service
Tokens · Edit*):

```bash
ACCT=<account-id>
# create
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCT/access/service_tokens" \
  -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"helix-cli-<teammate>"}'
# -> result.client_id + result.client_secret (secret shown ONCE — hand it to them securely)
```

Then add that token id to the Helix app's **Service Auth** (`non_identity`)
policy `include` (same pattern as §5e). Give the teammate their `client_id` /
`client_secret` via a password manager or secret share — **never in chat or a
committed file.**

To revoke a teammate's CLI access later: delete their service token
(`DELETE …/access/service_tokens/{id}`) or remove it from the policy.

---

## Security notes

- **Tier 1 (browser)** is gated by Cloudflare Access SSO — only allowlisted
  emails get in, enforced at Cloudflare's edge before any traffic reaches the
  box. Removing an email revokes access immediately.
- **A service token is a credential.** Anyone holding the id/secret can submit
  jobs (spending your LLM provider keys). Use **per-teammate** tokens, store
  them in a secret manager, and revoke on offboarding. Rotate with
  `POST …/access/service_tokens/{id}/rotate`.
- The Helix API itself has **no built-in auth** — Cloudflare Access is the
  whole gate. Never expose the box's port directly (the tunnel keeps it
  inbound-free); never add a public DNS record that bypasses Access.
