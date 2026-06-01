---
name: helix-setup
description: One-time installation + onboarding for Helix on a developer's machine. Use whenever Helix is not yet running locally, the user mentions "set up helix", "install helix", "first time using helix", or when a helix-compile / helix-eval / helix-export request hits a missing prerequisite (no `.helix.toml`, no `$HELIX_HOME`, stack down, missing provider keys). Idempotent — re-runs detect what's already done and skip it.
---

# helix-setup

Brings a developer's machine from "no Helix at all" to a running stack
with a working `.helix.toml` in the current repo. Idempotent — each step
detects "already done" and skips.

## Goal state

When this skill is finished:

- Helix is cloned at `$HELIX_HOME` (default `~/GitHub/helix`).
- The workspace venv is synced (`uv sync` ran once at `$HELIX_HOME`),
  so `uv run --project $HELIX_HOME helix …` is instant.
- The current repo has a `.helix.toml` at its root.
- `$HELIX_HOME/deploy/.env` has the developer's provider API keys.
- The stack is up at `http://127.0.0.1:<host_port>` (default :7000).
- `uv run --project $HELIX_HOME helix status` shows every service `Up`.

The agent should walk these steps in order, **checking each precondition
before doing anything**. Do not re-run a step that's already complete.

## Defaults to assume unless overridden

| Variable | Default | How to override |
|---|---|---|
| `HELIX_HOME` | `~/GitHub/helix` | env var set by the developer |
| Helix repo | `https://github.com/justanotheratom/helix` | (fork URL) |
| Consumer worktree | the current working directory | `cd <repo>` first |

## Step 1 — Verify host prerequisites

These are not auto-installable by the agent (system-level installers).
Detect each; if any is missing, **stop and tell the user the install
command**, then ask them to re-invoke this skill.

```bash
command -v docker >/dev/null 2>&1 || echo "MISSING docker"
command -v uv     >/dev/null 2>&1 || echo "MISSING uv"
command -v git    >/dev/null 2>&1 || echo "MISSING git"
```

Suggested install commands when missing:

- **docker** — Docker Desktop (https://www.docker.com/products/docker-desktop/)
  or `brew install --cask docker` on macOS. Ensure `docker info` works.
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh` then restart
  the shell so `~/.local/bin` is on PATH (or `brew install uv`).
- **git** — present on essentially every dev machine; install from
  https://git-scm.com/downloads if not.

Do not proceed until all three are present.

## Step 2 — Clone Helix to `$HELIX_HOME`

```bash
: "${HELIX_HOME:=$HOME/GitHub/helix}"
export HELIX_HOME
if [ ! -d "$HELIX_HOME/.git" ]; then
  mkdir -p "$(dirname "$HELIX_HOME")"
  git clone https://github.com/justanotheratom/helix "$HELIX_HOME"
fi
```

If the clone fails with `Repository not found` / `Permission denied`,
the Helix repo is access-controlled. Ask the developer to verify their
GitHub credentials (`gh auth status`) or to confirm they have read access,
then re-invoke this skill.

If the clone succeeded but is on an old commit, `git -C "$HELIX_HOME"
pull --ff-only` to fast-forward.

## Step 3 — Sync the workspace venv

```bash
( cd "$HELIX_HOME" && uv sync ) >/dev/null
```

This is fast after the first run. Verify the `helix` entry point exists:

```bash
"$HELIX_HOME/.venv/bin/helix" --help | head -1   # expect: usage: helix [-h] {init,...}
```

## Step 4 — Scaffold `.helix.toml` in the consumer repo

In the **developer's current worktree** (not `$HELIX_HOME`):

```bash
if [ ! -f .helix.toml ]; then
  uv run --project "$HELIX_HOME" helix init   # non-tty mode uses defaults
fi
```

`helix init` derives a safe `repo_id` from the directory name and writes
sensible defaults for `base`, `overlay.roots`, `env.lockfile`, ports,
and the Langfuse project id. **Show the generated file to the developer**
and ask whether the defaults match their repo layout:

- `base` should point at the dir that's both their PYTHONPATH root *and*
  the parent of their program-version dirs. Defaults to `"src"`; common
  alternatives: `"backend/ai"`, `"server"`, `"app"`. Edit `.helix.toml`
  if the default is wrong.
- `overlay.roots` is the editable subset of `base` whose contents ship
  per-job (default `["programs"]`). Adjust if a different dir name is used.
- `env.lockfile` is the consumer's `uv.lock` for the *job environment*
  (must include `dspy-ai`, `langfuse`, `litellm`, etc.). Defaults to
  `<base>/uv.lock`.

Re-run `helix init --force` after editing if needed (or just edit the
file in place — Helix re-reads it per command).

## Step 5 — Write provider keys to `deploy/.env` (interactive)

`helix bootstrap` is interactive (uses `getpass` for secret keys). Do not
attempt to drive it from the agent's bash. **Instruct the developer** to
run, in their own terminal:

```bash
uv run --project "$HELIX_HOME" helix bootstrap
```

It prompts for `OPENAI_API_KEY`, `GEMINI_API_KEY` (optional),
`ANTHROPIC_API_KEY` (optional), `OPENROUTER_API_KEY` (optional) and
writes `$HELIX_HOME/deploy/.env` from the template. Wait for the
developer to confirm completion before proceeding.

These four are a **starter set**, not the full list. The worker only forwards
a provider key if it's present in `$HELIX_HOME/deploy/.env`, so **add any other
provider keys your compile/eval configs reference** (e.g. `CEREBRAS_API_KEY`,
`GROQ_API_KEY`, `TOGETHER_API_KEY`) before treating the stack as ready — grep
your configs' `api_key_env:` values to find them. A config that names a key
missing from `deploy/.env` fails on its first LM call.

A non-interactive alternative is `cp $HELIX_HOME/deploy/.env.example
$HELIX_HOME/deploy/.env` and editing the keys in place.

Check completion:

```bash
test -f "$HELIX_HOME/deploy/.env" && echo "OK env present"
```

## Step 6 — Choose endpoint: local stack vs shared remote

Helix can run as the developer's **own local stack**, or the CLI can point at a
**shared remote** Helix (a team box) and skip running a stack entirely. Decide
which before bringing anything up.

| | Local stack | Shared remote |
|---|---|---|
| `HELIX_BASE_URL` | unset → `http://127.0.0.1:<host_port>` (default 7000) | `https://<your-helix-host>` |
| Auth | none (API is unauthenticated on localhost) | Cloudflare Access service token: `CF_ACCESS_CLIENT_ID` + `CF_ACCESS_CLIENT_SECRET` |
| Run `helix up` (step 7)? | yes | no — the remote runs jobs |

- **Local** is the default — nothing to set; continue to step 7.
- **Shared remote** — set `HELIX_BASE_URL` and the two service-token vars, then
  **skip step 7** (you don't run a stack; submits land on the remote). The CLI
  sends the `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers
  automatically when those vars are set, and no-ops them when unset.
  - You don't self-issue the token — an admin mints a **per-teammate**
    Cloudflare Access service token; see `team-access.md` §Tier 2 and
    `self-hosting.md` §5e in the Helix repo for issuance.
  - **Where to put the vars:** the CLI auto-loads the consumer's
    **main-worktree-root `.env`** (resolved via `git rev-parse --git-common-dir`,
    so it's found even from a linked git worktree, which has no `.env` of its
    own). Put `HELIX_BASE_URL` / `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET`
    there instead of exporting them — a real shell variable still overrides the
    file. Keep that `.env` gitignored; it holds a credential.

## Step 7 — Bring the stack up (local only)

First run builds the `helix-api` / `helix-worker` images (one `uv sync`
inside each, ~5-10 min) and pulls Postgres / MinIO / Redis / Langfuse.
Subsequent `helix up` is a few seconds.

```bash
uv run --project "$HELIX_HOME" helix up
```

Watch for the line `helix is up → http://127.0.0.1:<port>`.

## Step 8 — Verify

```bash
uv run --project "$HELIX_HOME" helix status
uv run --project "$HELIX_HOME" helix doctor
```

`status` should list every `helix-*` and `langfuse-*` container with
`Up` and most healthy. `doctor` should report `OK — Helix code is
consumer-agnostic` (it loads the consumer's `.helix.toml` and audits
the Helix code tree for any coupling — should always be clean for
upstream Helix).

## Optional — shell alias for interactive use

For developers who'll be running `helix` from a terminal (not via the
agent), drop an alias into their shell init:

```bash
echo "export HELIX_HOME=$HELIX_HOME"                          >> ~/.zshrc
echo "alias helix='uv run --project \$HELIX_HOME helix'"      >> ~/.zshrc
```

Then a new shell can run `helix submit compile <cfg>` directly.

## What to do next

Once setup completes, common follow-ups:

- `helix-compile` — submit a DSPy compile job.
- `helix-eval` — eval an existing compile.
- `helix-export` — materialize a job's `results/<NNNN>/` for a downstream
  deploy step.
- `helix` — full CLI command reference.

## Idempotency cheat sheet (what re-runs do)

| Step | First run | Subsequent runs |
|---|---|---|
| 1 prerequisite check | passes | passes |
| 2 clone | clones | `[ -d .git ]` → skip (optionally `pull --ff-only`) |
| 3 uv sync | downloads | `Audited in 0ms` (instant) |
| 4 helix init | writes `.helix.toml` | refuses (`already exists; pass --force`) |
| 5 helix bootstrap | writes `.env` | refuses (`already exists; pass --force`) |
| 6 choose endpoint | local default / set remote vars | unchanged |
| 7 helix up (local) | builds + ups (slow) | recreates only on config change |
| 8 verify | shows healthy | shows healthy |

So running this skill again after a fresh checkout is safe and cheap.
