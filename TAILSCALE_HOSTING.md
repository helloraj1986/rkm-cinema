# RKM Watchlist — Tailscale hosting (setup + commands)

The dashboard is a static file (`dashboard.html` in this folder). Serving it
over Tailscale is a 2-step setup. Pick ONE server option (A or B), then run the
Tailscale command (C).

## A) Native — Python http.server (no Docker)
Windows: run PowerShell as Administrator once:
```powershell
# one-time service install (runs at logon, survives logoff/reboot)
schtasks /Create /TN "RKM Watchlist" /TR "powershell -NoProfile -WindowStyle Hidden -Command \"Start-Process python -ArgumentList '-m','http.server','8123','--bind','127.0.0.1','--directory','D:\hermes_agent\hermes-workspace\media\watchlist'\" -WindowStyle Hidden" /SC ONLOGON /RL HIGHEST /F
```
Note: needs Python on Windows (`python --version`). If missing, use option B.

## B) Docker — nginx container (auto-start with Docker Desktop)
`docker-compose.yml` (place next to this file):
```yaml
services:
  watchlist:
    image: nginx:alpine
    container_name: rkm-watchlist
    restart: unless-stopped
    ports:
      - "127.0.0.1:8123:80"
    volumes:
      - D:\media\watchlist:/usr/share/nginx/html:ro
```
Run once: `docker compose up -d`

## C) Expose over Tailscale (run on the desktop)
```powershell
tailscale serve --bg http:80 http://127.0.0.1:8123
```
Then open on ANY device in your tailnet:
`http://<rkm-hp>.ts.net/dashboard.html`
(replace `<rkm-hp>` with the desktop's MagicDNS name)

- Plain-http mode on purpose — keeps the page + Radarr/Sonarr calls all HTTP
  (no mixed-content blocking).
- `tailscale serve --bg` persists across reboots automatically.
- Remove later: `tailscale serve --bg --https 443 off` (or `tailscale serve reset`).

## Security
- Tailnet-only. The dashboard embeds your *arr API keys — do NOT use
  `tailscale funnel` (public) for this.
- Bind the local server to 127.0.0.1 only (done above), so only tailscale
  serve (and localhost) can reach it.

## Regenerating after URL change
Edit `D:\media\watchlist\.env`:
```
BROWSER_RADARR_URL=http://<rkm-hp>:7878
BROWSER_SONARR_URL=http://<rkm-hp>:8989
```
then rerun: `python D:\media\watchlist\build_dashboard.py`
(or just ask me — the daily cron will pick it up next build).