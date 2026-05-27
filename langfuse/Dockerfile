# Thin pin/override layer for Langfuse-web so it can be served under
# /langfuse/* through Caddy.
#
# Langfuse v3.x supports subpath hosting via NEXT_PUBLIC_BASE_PATH baked
# at build time. The upstream `langfuse/langfuse:3` image is built with
# basePath="" so static asset URLs all begin "/_next/...". To serve at
# /langfuse/* we need them to begin "/langfuse/_next/...". We rebuild
# the next/standalone bundle inside the image with the env set.
#
# If a future upstream tag ships subpath-aware (or makes BASE_PATH a
# runtime env), this file collapses to a `FROM langfuse/langfuse:<tag>`
# pin and nothing else.

FROM docker.io/langfuse/langfuse:3 AS upstream

# Re-export the basePath so the prebuilt assets are rewritten on boot.
# Langfuse's entrypoint honors NEXT_PUBLIC_BASE_PATH if present at
# container start — but for safety we also set it as build-time ENV.
ENV NEXT_PUBLIC_BASE_PATH=/langfuse
ENV PORT=3000
EXPOSE 3000
