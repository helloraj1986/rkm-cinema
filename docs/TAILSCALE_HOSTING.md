# Remote / phone access over Tailscale

The app is a **running Docker stack** (nginx `web` on host port **8124** + the `api`
container + the bundled **Jellyfin** on **8098**). There is no static file to serve
any more — this doc used to describe hosting a generated `dashboard.html`, which no
longer exists.

## 1) Make sure the stack is up (on the desktop)

```powershell
cd D:\hermes_agent\hermes-workspace\projects\rkm-cinema
.\rkm.ps1 status
```

Want `== verdict == everything looks healthy`. If it says `UNREACHABLE`, start it:

```powershell
docker compose -p rkm-bundled up -d
```

## 2) Expose it to your tailnet (once — the rule persists across reboots)

```powershell
tailscale serve --bg http:80 http://127.0.0.1:8124
```

Then open on ANY device in your tailnet:
`http://<rkm-hp>.ts.net/` — replace `<rkm-hp>` with the desktop's MagicDNS name
(e.g. `http://rkm-hp.tail8d5e8.ts.net/`).

The bundled **Jellyfin** keeps its own port, so its web UI / mobile app talks to the
machine directly on `http://<rkm-hp>:8098` (Tailscale already routes that).

- Plain-http mode on purpose — keeps the page and its `/api` + Jellyfin calls all
  HTTP, so nothing is blocked as mixed content.
- `tailscale serve --bg` persists across reboots automatically — it is not part of
  the Docker stack and needs no re-run after a restart.
- Undo later: `tailscale serve reset` (or `tailscale serve --bg --https 443 off`).

## 3) Optional — deep-links that work from the phone

"Open in Jellyfin" uses whatever `.env` says:

```
RKM_JELLYFIN_BROWSER=http://<rkm-hp>.ts.net:8098
```

Then apply it (`render_config.py` writes it into `.rkm.env` for the api):

```powershell
.\rkm.ps1 deploy
```

## Security

- **Tailnet-only.** Use `tailscale serve` — never `tailscale funnel` (public).
  Nothing here should be reachable by anyone who is not on your tailnet.
- Keep the Docker ports published on the host only as they are; Tailscale is the
  single front door, and the `api` container holds every secret (TMDB, Radarr,
  Sonarr, Prowlarr, qBittorrent, Jellyfin admin).

## If the phone shows the OLD app

That is a cached bundle, not a broken deploy: hard-refresh or close/reopen the tab.
Every build writes cache-busted asset filenames, so a normal reload is usually enough.
