#!/usr/bin/env bash
# deploy/build.sh — stage the Helix source as the image build context.
#
# Generic, repo-agnostic images: NO consumer repo is baked. The build context
# (`.helix-build/`) carries only the Helix source dirs. Built from the WORKING
# TREE so local changes are testable without committing (the `helix dev up`
# path). Consumer code arrives at runtime as a content-addressed snapshot, and
# the job env is built from the snapshot's uv.lock — neither is baked here.
#
# Standalone-repo layout: Helix IS the repo root (api/, common/, worker/,
# runtime/, openapi/ at the top level — no helix/ prefix).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SNAPSHOT_DIR="$REPO_ROOT/.helix-build"
rm -rf "$SNAPSHOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

echo "Staging Helix source → .helix-build/ (working tree)"
# Only the dirs the api/worker Dockerfiles COPY from. The UI builds from its
# own context (deploy/docker-compose.yml → ../ui), so it isn't staged here.
tar -c \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    api common worker runtime openapi | tar -x -C "$SNAPSHOT_DIR"

echo "Build context ready at .helix-build/"
echo "Run: docker compose -p <repo_id>-helix -f deploy/docker-compose.yml --env-file deploy/.env build"
