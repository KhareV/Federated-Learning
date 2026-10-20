#!/bin/sh
# Start NHM inside the container: install the frontend packages on first run (Linux builds live in named volumes, never the host's),
# forward the browser-facing port to the loopback-bound frontend, then hand over to the normal launcher.
set -e
cd /app
git config --global --add safe.directory /app
[ -x frontend/node_modules/.bin/vite ] || (cd frontend && npm ci --no-audit --no-fund)
[ -d frontend/clerk-sdk/node_modules ] && [ -n "$(ls -A frontend/clerk-sdk/node_modules 2>/dev/null)" ] || (cd frontend/clerk-sdk && npm ci --no-audit --no-fund)
# the launcher binds 127.0.0.1 only; the frontend proxies the product API, so one forwarded port is all the browser needs
socat TCP-LISTEN:4180,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:4173 &      # 4180, not 4173: the launcher refuses to start if anything already holds 4173
exec python -m scripts.run_nhm "$@"
