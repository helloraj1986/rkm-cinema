# ============================================================================
# RKM bundled stack - one-command bootstrap (Windows PowerShell)
#   run:  .\bootstrap.ps1
# Reads the SINGLE repo-level .env (copy .env.example and fill it in),
# renders .rkm.env for the api container, starts the isolated stack
# (api+web+jellyfin), runs the Jellyfin provisioner, then restarts api so it
# picks up the freshly-created Jellyfin API key.
# ASCII only - PowerShell 5.1 misreads UTF-8 without BOM.
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== RKM bundled stack bootstrap ==" -ForegroundColor Cyan

if (!(Test-Path .\.env)) {
    if (Test-Path .\.env.example) { Copy-Item .\.env.example .\.env }
    Write-Host "Created .env from .env.example." -ForegroundColor Yellow
    Write-Host "Open .env and fill in your keys (TMDB_API_KEY, RADARR/SONARR/PLEX/EMBY/JELLYFIN ...), then re-run bootstrap." -ForegroundColor Yellow
    Write-Host "Jellyfin backend: leave RKM_JELLYFIN_ADMIN_PASSWORD blank on first run - a password is generated and saved to .env automatically." -ForegroundColor Yellow
}

# --- Docker present? ---
docker version --format "x" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running/installed. Start Docker Desktop, then re-run." -ForegroundColor Red
    exit 1
}

# --- Render config (repo .env -> .rkm.env for the api container) ---
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
Write-Host "Rendering .env -> .rkm.env ..." -ForegroundColor Cyan
& $py render_config.py
if ($LASTEXITCODE -ne 0) { Write-Host "render_config.py failed." -ForegroundColor Red; exit 1 }

$dp = "8124"
try { $dp = (Select-String -Path .env -Pattern "^RKM_DASHBOARD_PORT=(.*)$").Matches[0].Groups[1].Value.Trim() } catch {}

# --- Start the stack (isolated project name rkm-bundled) ---
Write-Host "Starting api + web + jellyfin (project rkm-bundled) ..." -ForegroundColor Cyan
docker compose -p rkm-bundled up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose up failed." -ForegroundColor Red; exit 1 }

# --- Wait for the API to be healthy ---
Write-Host "Waiting for API health ..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $s = (Invoke-WebRequest -Uri "http://localhost:$dp/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode
        if ($s -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (!$ready) { Write-Host "API not healthy after 120s - check: docker compose -p rkm-bundled logs api" -ForegroundColor Yellow }

# --- Run the Jellyfin provisioner (creates admin + API key + libraries) ---
Write-Host "Running provisioner (Jellyfin setup) ..." -ForegroundColor Cyan
docker compose -p rkm-bundled --profile provision run --rm --build provisioner
if ($LASTEXITCODE -ne 0) {
    Write-Host "Provisioner had issues (see above). Jellyfin may need one manual setup at http://localhost:8098/web" -ForegroundColor Yellow
}

# --- Restart api so it loads the runtime config (the new Jellyfin API key) ---
# `up -d api` alone does NOT recreate an unchanged container; force-recreate so
# a fresh process re-reads /shared/runtime.json (Config() is cached per process).
Write-Host "Restarting api to load runtime config ..." -ForegroundColor Cyan
docker compose -p rkm-bundled up -d --force-recreate api

Write-Host ""
Write-Host "Bundled stack ready:" -ForegroundColor Green
Write-Host "  Dashboard:  http://localhost:$dp/"
Write-Host "  Jellyfin:   http://localhost:8098/web"
Write-Host "  API health: http://localhost:$dp/api/health"
Write-Host ""
Write-Host "Isolated from your prod stack (own network rkm-exp, own ports, media root from RKM_MEDIA_PATH in .env)." -ForegroundColor DarkGray
Write-Host "Teardown (keeps data):  docker compose -p rkm-bundled down" -ForegroundColor DarkGray
Write-Host "Full reset (DELETES experiment data):  docker compose -p rkm-bundled down -v" -ForegroundColor DarkGray