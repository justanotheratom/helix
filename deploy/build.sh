#!/usr/bin/env bash
# deploy/build.sh — stage the Helix source as the image build context.
#
# Generic, repo-agnostic images: NO consumer repo is baked. Consumer code
# arrives at runtime as a content-addressed snapshot, and the job env is built
# from the snapshot's uv.lock at job time. The Helix images themselves pin
# their deps via the WORKSPACE uv.lock at this repo root (no inline `pip
# install` lines in the Dockerfiles).
#
# Built from the WORKING TREE so local changes are testable without committing
# (`helix dev up`). Standalone-repo layout: api/, common/, worker/, runtime/,
# openapi/ at the top level.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SNAPSHOT_DIR="$REPO_ROOT/.helix-build"
rm -rf "$SNAPSHOT_DIR"
mkdir -p "$SNAPSHOT_DIR"

echo "Staging Helix source → .helix-build/ (working tree)"
# Workspace root + lock + every member's pyproject + source the Dockerfiles
# need (api/, worker/, runtime/, openapi/, common/, and the cli pyproject so
# `uv sync` can resolve the workspace).
tar -c \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    --exclude='*/.venv' \
    pyproject.toml uv.lock \
    api common worker runtime openapi cli/pyproject.toml | tar -x -C "$SNAPSHOT_DIR"

echo "Build context ready at .helix-build/"
echo "Run: docker compose -p <repo_id>-helix -f deploy/docker-compose.yml --env-file deploy/.env build"
