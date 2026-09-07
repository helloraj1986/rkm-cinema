#!/usr/bin/env bash
# ============================================================================
# RKM bundled stack - one-command bootstrap (Linux/macOS)
#   run:  ./bootstrap.sh
# Reads the SINGLE repo-level .env (copy .env.example and fill it in),
# renders .rkm.env for the api container, starts the isolated stack
# (api+web+jellyfin), runs the Jellyfin provisioner, then restarts api so it
# picks up the freshly-created Jellyfin API key.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "== RKM bundled stack bootstrap =="
if [ ! -f .env ]; then
    if [ -f .env.example ]; then cp .env.example .env; fi
    echo "Created .env from .env.example."
    echo "Open .env and fill in your keys (TMDB_API_KEY, RADARR/SONARR/PLEX/EMBY/JELLYFIN ...), then re-run bootstrap."
    echo "Jellyfin backend: leave RKM_JELLYFIN_ADMIN_PASSWORD blank on first run - a password is generated and saved to .env automatically."
fi

command -v docker >/dev/null || { echo "Docker is not installed/run."; exit 1; }

echo "Rendering .env -> .rkm.env ..."
python3 render_config.py || { echo "render_config.py failed."; exit 1; }

DP="$(sed -n 's/^RKM_DASHBOARD_PORT=\(.*\)$/\1/p' .env | tr -d '\r')"
DP="${DP:-8124}"

echo "Starting api + web + jellyfin (project rkm-bundled) ..."
docker compose -p rkm-bundled up -d --build

echo "Waiting for API health ..."
ready=""
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${DP}/api/health" >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
done
[ -n "$ready" ] || echo "API not healthy after 120s - check: docker compose -p rkm-bundled logs api"

echo "Running provisioner (Jellyfin setup) ..."
docker compose -p rkm-bundled --profile provision run --rm --build provisioner || \
    echo "Provisioner had issues; Jellyfin may need one manual setup at http://localhost:8098/web"

echo "Restarting api to load runtime config ..."
docker compose -p rkm-bundled up -d --force-recreate api

echo ""
echo "Bundled stack ready:"
echo "  Dashboard:  http://localhost:${DP}/"
echo "  Jellyfin:   http://localhost:8098/web"
echo "  API health: http://localhost:${DP}/api/health"
echo "Teardown: docker compose -p rkm-bundled down"
echo "Full reset (DELETES experiment data): docker compose -p rkm-bundled down -v"