# Helix

A self-contained, repo-agnostic job runner for DSPy compile/eval workflows.
A single local docker-compose stack owns the job lifecycle; any consumer repo
contributes only a `.helix.toml` and gets a durable queue, content-addressed
snapshots, per-job overlay isolation, a reproducible `uv`-built env, blob
artifacts, live logs, and Langfuse tracing.

This repository is **run-from-clone**: there is no published CLI or image
registry yet. You clone it, build the images locally, and run the CLI from
source against your consumer repo.

## Install the skills, then ask your agent

If you're using Claude Code (or any agent that supports
[`skills.sh`](https://www.skills.sh/) skills), the fastest way to start is
to install the Helix skills and then just describe what you want:

```bash
# In your consumer repo:
npx skills add justanotheratom/helix
```

Then talk to your agent:

> *"Set up helix in this repo."*
> *"Compile my DSPy program at `<base>/programs/<p>/<v>/compile.config.NNNN.yaml`."*
> *"Eval compile job `<uuid>` on the test split."*
> *"Export eval job `<uuid>` to a results dir."*

The `helix-setup` skill handles first-time installation end to end (clone
this repo, sync the workspace venv, scaffold `.helix.toml`, write provider
keys, bring the stack up); `helix-compile` / `helix-eval` / `helix-export`
drive the workflows; `helix` is the catch-all CLI reference. All four are
in `skills/` and installed by the command above.

Prefer driving Helix directly from the shell? Read on.

## Layout

```
api/        FastAPI control plane (queue, snapshots, artifacts, logs)
worker/     job worker (snapshot materialize → uv venv → run entrypoints)
runtime/    the DSPy compile/eval entrypoints (run inside the consumer venv)
common/     helix_config.py — the .helix.toml loader (stdlib-only)
cli/        the `helix` CLI (helix_cli)
openapi/    openapi.yaml (source of truth) + codegen.sh for the 3 clients
deploy/     docker-compose.yml, build.sh, Caddyfile, .env.example
```

## Prerequisites

- Docker (with `docker compose`)
- [`uv`](https://docs.astral.sh/uv/) on your host (for the CLI + image venvs)

## Run the stack from this clone

> Deploying for a **team on a remote VM** (incl. Langfuse, behind SSO, on a
> small box)? See **[docs/self-hosting.md](docs/self-hosting.md)** — the
> validated Hetzner + Cloudflare Tunnel path (full stack on an 8 GB VM,
> ~$16/mo, zero inbound ports).

```bash
git clone https://github.com/justanotheratom/helix ~/GitHub/helix
cd ~/GitHub/helix

# 1) Secrets / config (writes deploy/.env from deploy/.env.example):
cp deploy/.env.example deploy/.env   # then edit in your provider keys

# 2) Build the generic images from this working tree and bring the stack up.
#    `helix dev up` builds locally; `helix up` builds-if-missing.
deploy/build.sh
docker compose -p <repo_id>-helix -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

(`<repo_id>` comes from your consumer's `.helix.toml`. The wrapper commands
below derive it for you.)

## Use the CLI against a consumer repo

The CLI runs from this clone but operates on **your** repo (the one with a
`.helix.toml`). The repo is a uv workspace with the `helix` script defined in
`cli/pyproject.toml`, so a single `uv run --project` invocation handles it:

```bash
export HELIX_HOME=~/GitHub/helix

cd ~/your-consumer-repo          # has .helix.toml
uv run --project $HELIX_HOME helix doctor    # audits coupling
uv run --project $HELIX_HOME helix up        # bring the stack up
uv run --project $HELIX_HOME helix submit compile path/to/compile.config.yaml
uv run --project $HELIX_HOME helix status <job-id>
```

The first invocation syncs the workspace venv from `uv.lock` (one-time);
subsequent runs are instant. `HELIX_HOME` tells the stack commands where
Helix's `deploy/` lives; the consumer config (`repo_id`, ports, Langfuse
project) is read from the `.helix.toml` in the directory you run from.

A shell alias makes it shorter:

```bash
alias helix='uv run --project ~/GitHub/helix helix'
```

## Dev loop — edit Helix code without rebuilds

`helix dev up` bind-mounts this repo's source into the containers
(`deploy/docker-compose.dev.yml`), so code edits don't need an image rebuild
and **all data persists** (named volumes are untouched):

```bash
python -m helix_cli dev up        # source-mounted; api runs with --reload
# ...edit code...
#   api      → hot-reloads automatically
#   worker   → python -m helix_cli dev restart   (≈1s, not a rebuild)
#   runtime/ → picked up on the next job (fresh subprocess), no restart
python -m helix_cli dev up --rebuild   # only when deps / a Dockerfile change
```

A rebuild is only needed when dependencies or a `Dockerfile` change. Jobs,
snapshots, and artifacts survive restarts and rebuilds alike; only
`docker compose down -v` wipes them.

## New consumer

```bash
cd ~/new-repo
uv run --project ~/GitHub/helix helix init   # scaffolds a .helix.toml (validated)
uv run --project ~/GitHub/helix helix up
```

## Concepts

- **Content-addressed snapshots**: on submit, the consumer's base dir is
  scoped, digested, and stored once in MinIO; the worker materializes it as
  the overlay lowerdir. Identical trees dedupe; a changed tree republishes.
- **Reproducible env**: the worker builds a `uv`-locked venv from the
  snapshot's `uv.lock` (the authoritative job environment) and runs the
  entrypoints with it.
- **out_of_band data**: large data declared in `[snapshot].out_of_band` is
  shipped as separate content-addressed blobs and mounted as extra overlay
  lowerdirs.
- **GC**: `helix gc` reclaims unreferenced snapshot blobs and orphan bundles.

## License

Helix is source-available under the
[PolyForm Shield License 1.0.0](https://polyformproject.org/licenses/shield/1.0.0)
(see [LICENSE](./LICENSE)). Plain-English summary, **not legal advice**:

- ✅ **You can self-host Helix for your own purposes** — internal or commercial
  — including running compiles/evals for your own products and services.
- ✅ **You can modify it**, fork it, and use those changes internally.
- ❌ **You cannot use it to build or operate a product that competes with
  Helix itself** (e.g. a hosted "DSPy job runner as a service" derived from
  this code).

That's the whole rule. If your use is "we want a local DSPy compile/eval
stack for our app," you're fine. If your use is "we want to sell a Helix
look-alike," you're not. The full license text in `LICENSE` is authoritative.

This is **source-available**, not OSI open-source — some orgs have policies
that distinguish; check before adopting.
