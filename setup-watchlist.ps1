# RKM Cinema - one-command deploy (run from D:\hermes_agent\hermes-workspace\projects\rkm-cinema)
# PowerShell:
#   cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
#   .\setup-watchlist.ps1
# Then open http://rkm-hp.tail8d5e8.ts.net:8123/ from any tailnet device.
#
# v2 stack: `api` (FastAPI, holds *arr/TMDB/Plex secrets) + `web` (nginx, serves the
# dashboard AND proxies /api -> api:8000). Secrets stay server-side; the browser only
# ever talks to nginx on :8123.
#
# NOTE: keep this file pure ASCII (no em-dashes, no smart quotes) - PowerShell 5.1
# misreads UTF-8-no-BOM and the em-dash byte 0x94 becomes a quote char, breaking parsing.

Write-Host "== RKM Cinema deploy ==" -ForegroundColor Cyan

# Path-agnostic: work from this script's own folder so compose finds docker-compose.yml
Set-Location $PSScriptRoot

# The live watchlist data lives at D:\hermes_agent\hermes-workspace\media\watchlist.json
# (kept in media/ because it is shared with the rest of the media stack). The api
# container mounts ../../media (i.e. /workspace/media) and reads it directly, so no
# copy is required. This fallback only mirrors the file in if this repo is checked
# out somewhere that lacks the sibling data dir.
if (!(Test-Path .\watchlist.json) -and (Test-Path ..\..\media\watchlist.json)) {
    Copy-Item ..\..\media\watchlist.json .\watchlist.json -Force
    Write-Host "Copied ..\..\media\watchlist.json -> .\watchlist.json" -ForegroundColor DarkGray
}

# Tear down any previous containers for a clean rebuild
docker compose down 2>$null | Out-Null

Write-Host "Building + starting api + web (nginx :8123)..." -ForegroundColor Cyan
docker compose up -d --build

if ($LASTEXITCODE -ne 0) {
    Write-Host "Deploy FAILED (exit $LASTEXITCODE). Is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

Write-Host "`nWaiting for services to start..."
Start-Sleep -Seconds 6
docker ps --filter "name=rkm" --format "{{.Names}}  {{.Status}}  {{.Ports}}"

Write-Host "`nLocal check:  http://localhost:8123/" -ForegroundColor Green
Write-Host "Tailnet URL:  http://rkm-hp.tail8d5e8.ts.net:8123/" -ForegroundColor Green
Write-Host "`nAPI health (must be 200):"
try { (Invoke-WebRequest -Uri http://localhost:8123/api/health -UseBasicParsing -TimeoutSec 10).StatusCode } catch { Write-Host "  API not reachable yet - check 'docker compose logs api'" -ForegroundColor Yellow }

Write-Host "`nIf the tailnet URL doesn't load from your phone, allow inbound TCP 8123 (run as admin):"
Write-Host "  New-NetFirewallRule -DisplayName 'RKM Cinema' -Direction Inbound -Protocol TCP -LocalPort 8123 -Action Allow" -ForegroundColor DarkGray
