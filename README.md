# Helix

A self-contained, repo-agnostic job runner for DSPy compile/eval workflows.
A single local docker-compose stack owns the job lifecycle; any consumer repo
contributes only a `.helix.toml` and gets a durable queue, content-addressed
snapshots, per-job overlay isolation, a reproducible `uv`-built env, blob
artifacts, live logs, and Langfuse tracing.

This repository is **run-from-clone**: there is no published CLI or image
registry yet. You clone it, build the images locally, and run the CLI from
source against your consumer repo.

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
`.helix.toml`). Point Python at this clone and run from your consumer worktree:

```bash
export HELIX_HOME=~/GitHub/helix
export PYTHONPATH="$HELIX_HOME/cli:$HELIX_HOME/common"

cd ~/your-consumer-repo          # has .helix.toml
python -m helix_cli doctor       # audit: no consumer coupling in Helix code
python -m helix_cli up           # bring the stack up (uses your repo_id/ports)
python -m helix_cli submit compile path/to/compile.config.yaml
python -m helix_cli status <job-id>
```

`HELIX_HOME` tells the stack commands where Helix's `deploy/` lives; the
consumer config (`repo_id`, ports, Langfuse project) is read from the
`.helix.toml` in the directory you run from.

## New consumer

```bash
cd ~/new-repo
python -m helix_cli init     # scaffolds a .helix.toml (validated)
python -m helix_cli up
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
