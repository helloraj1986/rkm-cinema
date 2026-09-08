"""Phase 0 probe: Jellyfin HLS output shapes (docs/HLS_PLAYER_PLAN.md §3/§6).

Authenticates against the bundled Jellyfin (admin creds from the project
.env), finds a real episode, and reports:

- the episode's playback-info facts (container / video codec / audio codec) —
  confirms which stream mode episodes take today;
- live ``master.m3u8`` output for the HLS variants the proxy must support:
  default (no codec params), remux-HLS (copy/copy), transcode-HLS
  (h264/aac [+bitrate]); master layout, media-playlist URIs, segment URI
  patterns, MIME types.

Output is REDACTED — tokens/URLs never printed. Run from the repo root:

    python3 scripts/probe_jellyfin_hls.py [--episode-title-substr "Our Lord"]

Re-verify on Jellyfin major upgrades (facts here are 10.11-specific).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("JELLYFIN_URL", "http://host.docker.internal:8098")
AUTH_HEADER = (
    'MediaBrowser Client="rkm-probe", Device="sandbox", '
    'DeviceId="rkm-hls-probe-01", Version="1.0"'
)

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> dict[str, str]:
    """Minimal .env loader (project .env holds RKM_JELLYFIN_ADMIN_*)."""
    out: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return out
    for raw in _ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def redact(url: str) -> str:
    """Strip api_key/query tokens from a URL for display."""
    return re.sub(r"api_key=[^&\s\"']+", "api_key=<redacted>", url)


def redact_body(body: str) -> str:
    """Redact any api_key=<token> that Jellyfin embeds in playlist URIs."""
    return re.sub(r"api_key=[^&\s\"']+", "api_key=<redacted>", str(body))


def http_get(url: str, *, expect_json: bool = False, timeout: int = 20):
    """GET with a JSON/plain split; returns (status, headers, body-or-dict)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = int(getattr(r, "status", 200))
            headers = {k.lower(): v for k, v in r.headers.items()}
            raw = r.read()
            body: object
            if expect_json:
                body = json.loads(raw)
            else:
                try:
                    body = raw.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    body = f"<{len(raw)} bytes binary>"
            return status, headers, body
    except urllib.error.HTTPError as e:
        return int(e.code), {k.lower(): v for k, v in e.headers.items()}, e.read().decode("utf-8", errors="replace")


def http_post_json(url: str, payload: dict, *, timeout: int = 20):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Emby-Authorization": AUTH_HEADER},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200)), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return int(e.code), json.loads(e.read().decode("utf-8", errors="replace") or "{}")


def hls_summary(status: int, headers: dict, body: str, label: str, uid: str = "") -> None:
    """Print a compact shape report for one playlist response."""
    lines = [l for l in str(body).splitlines() if l.strip()]
    print(f"\n=== {label} ===")
    print(f"HTTP {status}  Content-Type: {headers.get('content-type', '—')!r}")
    print(f"lines: {len(lines)}")
    # Jellyfin master playlists often carry X-Playback-Session-Id header.
    for h in ("x-playback-session-id", "transfer-encoding", "content-length"):
        if headers.get(h):
            print(f"  hdr {h}: {headers.get(h)}")
    for ln in lines[:25]:
        print(f"  | {redact_body(ln)}")
    if len(lines) > 25:
        print(f"  … (+{len(lines) - 25} lines)")


def probe_deep(master_url_builder, base: str, token: str, uid: str, ep_id: str, mid: str, video: dict, audio: list) -> None:
    """Extra Phase-0 shapes: segment MIME/Range, transcode media playlist,
    StartTimeTicks truncation (resume design), first-segment fetch."""
    import urllib.parse as up_mod

    def _first_uri(playlist_body) -> str | None:
        return next((l.strip() for l in str(playlist_body).splitlines()
                     if l.strip() and not l.startswith("#")), None)

    print("\n################ DEEP probes ################")
    # 1) remux media playlist + ONE segment fetch (MIME, size, Range support)
    remux_master = master_url_builder(VideoCodec="copy", AudioCodec="copy")
    st, _, body = http_get(remux_master)
    if st == 200:
        uri = _first_uri(body)
        if uri:
            mst, mhd, mbody = http_get(up_mod.urljoin(remux_master, uri), timeout=30)
            print(f"\n-- remux media playlist: HTTP {mst} type={mhd.get('content-type')}")
            if mst == 200:
                seg_uri = _first_uri(mbody)
                if seg_uri:
                    full = up_mod.urljoin(remux_master, seg_uri)
                    sst, shd, sbody = http_get(full, timeout=60)
                    print(f"-- first remux segment GET: HTTP {sst} type={shd.get('content-type')} "
                          f"bytes={shd.get('content-length')}")
                    rreq = urllib.request.Request(full, method="GET",
                                                  headers={"Range": "bytes=0-1023"})
                    try:
                        with urllib.request.urlopen(rreq, timeout=30) as r:
                            print(f"-- segment Range bytes=0-1023: HTTP {int(getattr(r, 'status', 200))} "
                                  f"Accept-Ranges={r.headers.get('Accept-Ranges')} "
                                  f"Content-Range={r.headers.get('Content-Range')} "
                                  f"type={r.headers.get('Content-Type')}")
                    except urllib.error.HTTPError as e:
                        print(f"-- segment Range: HTTP {e.code} (no range support)")

    # 2) transcode media playlist (does it serve fMP4 or TS?)
    tr_master = master_url_builder(VideoCodec="h264", AudioCodec="aac", MaxAudioChannels=2)
    st, _, body = http_get(tr_master)
    if st == 200:
        uri = _first_uri(body)
        if uri:
            mst, mhd, mbody = http_get(up_mod.urljoin(tr_master, uri), timeout=30)
            print(f"\n-- transcode media playlist: HTTP {mst} type={mhd.get('content-type')}")
            if mst == 200:
                for ln in str(mbody).splitlines()[:6]:
                    print(f"  | {redact_body(ln)}")
                seg_uri = _first_uri(mbody)
                if seg_uri:
                    full = up_mod.urljoin(tr_master, seg_uri)
                    sst, shd, sbody = http_get(full, timeout=90)
                    print(f"-- first transcode segment GET: HTTP {sst} type={shd.get('content-type')} "
                          f"bytes={shd.get('content-length')}")

    # 3) StartTimeTicks truncation (resume design): does a mid-point master
    #    yield a VOD playlist that starts at that tick?
    st_master = master_url_builder(StartTimeTicks=600_000_000)  # 60 s in
    st, _, body = http_get(st_master)
    print(f"\n-- StartTimeTicks=600s master: HTTP {st}")
    if st == 200:
        uri = _first_uri(body)
        if uri:
            mst, mhd, mbody = http_get(up_mod.urljoin(st_master, uri), timeout=30)
            print(f"-- StartTimeTicks media playlist: HTTP {mst} lines={len(str(mbody).splitlines())}")
            seg_lines = [l for l in str(mbody).splitlines()
                         if l.strip() and not l.startswith("#")]
            print(f"   segment count: {len(seg_lines)}")
            if seg_lines:
                print(f"   first segment: {redact_body(seg_lines[0][:140])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode-title-substr", default="Our Lord",
                    help="substring to pick ONE episode by name")
    ap.add_argument("--deep", action="store_true",
                    help="run the extra deep probes (segments MIME/Range, transcode playlist, StartTimeTicks)")
    args = ap.parse_args()

    env = _load_env()
    user = os.environ.get("RKM_JELLYFIN_ADMIN_USER") or env.get("RKM_JELLYFIN_ADMIN_USER")
    pw = os.environ.get("RKM_JELLYFIN_ADMIN_PASSWORD") or env.get("RKM_JELLYFIN_ADMIN_PASSWORD")
    if not (user and pw):
        print("ERROR: need RKM_JELLYFIN_ADMIN_USER/PASSWORD in project .env or env", file=sys.stderr)
        return 2

    # --- auth -------------------------------------------------------------
    url = f"{BASE}/Users/AuthenticateByName"
    req = urllib.request.Request(
        url,
        data=json.dumps({"Username": user, "Pw": pw}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Emby-Authorization": AUTH_HEADER},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            auth = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"auth failed: {e}", file=sys.stderr)
        return 1
    token = auth["AccessToken"]
    uid = auth["User"]["Id"]
    print(f"authenticated user={auth['User'].get('Name')} (token redacted)")
    q = lambda **kw: "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in kw.items())

    # --- find a real episode ----------------------------------------------
    # 1) series named like 3 Body Problem; 2) first episode whose title
    # matches the --episode-title-substr; fall back to episode #1 of that show.
    items_url = f"{BASE}/Users/{uid}/Items?Recursive=true&IncludeItemTypes=Series&Fields=Name&{q(**{'api_key': token})}"
    st, hd, series = http_get(items_url, expect_json=True)
    shows = [it for it in (series.get("Items") or [])
             if "3 body" in str(it.get("Name", "")).lower()]
    if not shows:
        shows = series.get("Items") or []
    if not shows:
        print("no Series found in library", file=sys.stderr)
        return 1
    show = shows[0]
    print(f"\nseries: {show.get('Name')} (id {show.get('Id')})")

    ep_url = (f"{BASE}/Users/{uid}/Items?ParentId={show['Id']}"
              f"&IncludeItemTypes=Episode&Recursive=true"
              f"&SortBy=IndexNumber,ParentIndexNumber&{q(**{'api_key': token})}")
    st, hd, epd = http_get(ep_url, expect_json=True)
    eps = epd.get("Items") or []
    want = [e for e in eps if args.episode_title_substr.lower()
            in str(e.get("Name", "")).lower()]
    ep = want[0] if want else (eps[0] if eps else None)
    if not ep:
        print("no episodes under chosen series", file=sys.stderr)
        return 1
    rt = int(ep.get("RunTimeTicks") or 0)
    print(f"episode: S{ep.get('ParentIndexNumber')}E{ep.get('IndexNumber')} "
          f"'{ep.get('Name')}' (id {ep['Id']}, runtime {rt / 10_000_000:.1f}s)")

    # --- playback-info facts ----------------------------------------------
    pi_url = f"{BASE}/Items/{ep['Id']}/PlaybackInfo?{q(**{'api_key': token})}"
    st, pi = http_post_json(pi_url, {
        "UserId": uid, "StartTimeTicks": 0,
        "AutoOpenLiveStream": False, "MediaSourceId": "",
    })
    ms = ((pi.get("MediaSources") or [{}])[0]) if st == 200 else {}
    streams = ms.get("MediaStreams") or []
    video = next((s for s in streams if s.get("Type") == "Video"), {})
    audio = [s for s in streams if s.get("Type") == "Audio"]
    print(f"\n-- playback-info (MediaSource '{ms.get('Id')}') --")
    print(f"container: {ms.get('Container')}   size: {ms.get('Size')}  "
          f"path-mountable: {ms.get('Path') is not None}")
    print(f"video: codec={video.get('Codec')} profile={video.get('Profile')} "
          f"{video.get('Width')}x{video.get('Height')} depth={video.get('BitDepth')} "
          f"bitrate={video.get('BitRate')}")
    for a in audio:
        print(f"audio[{a.get('Index')}]: codec={a.get('Codec')} "
              f"lang={a.get('Language')} channels={a.get('Channels')} "
              f"bitrate={a.get('BitRate')} title={a.get('DisplayTitle')!r}")

    # --- HLS master probes -------------------------------------------------
    mid = ms.get("Id") or ep["Id"]
    def master(**extra) -> str:
        params = {"api_key": token, "MediaSourceId": mid}
        params.update(extra)
        return f"{BASE}/Videos/{ep['Id']}/master.m3u8?{q(**params)}"

    print("\n################ HLS master variants ################")
    variants = {
        "HLS default (no codec params)": {},
        "HLS remux (VideoCodec=copy&AudioCodec=copy)": {"VideoCodec": "copy", "AudioCodec": "copy"},
        "HLS audio-transcode (VideoCodec=copy&AudioCodec=aac)": {"VideoCodec": "copy", "AudioCodec": "aac", "MaxAudioChannels": 2},
        "HLS transcode (h264/aac)": {"VideoCodec": "h264", "AudioCodec": "aac", "MaxAudioChannels": 2},
        "HLS transcode + 8Mbps": {"VideoCodec": "h264", "AudioCodec": "aac",
                                  "MaxAudioChannels": 2, "MaxStreamingBitrate": 8_000_000},
    }
    if len(audio) > 1:
        variants["HLS + AudioStreamIndex=1"] = {"AudioStreamIndex": audio[1].get("Index")}
    media_sampled = 0
    for label, extra in variants.items():
        murl = master(**extra)
        st, hd, body = http_get(murl)
        print(f"\n---- {label}")
        print(f"URL: {redact(murl)}")
        hls_summary(st, hd, body, f"master {label}")
        if st != 200:
            continue
        # Follow the FIRST media-playlist URI (relative or absolute) to learn
        # segment shapes. Only sample 2 variants (default + remux) to keep the
        # probe light and avoid spawning many live transcode sessions.
        if media_sampled >= 2:
            continue
        uri = None
        for ln in str(body).splitlines():
            if ln.startswith("#"):
                continue
            uri = ln.strip()
            break
        if not uri:
            continue
        media_sampled += 1
        purl = urllib.parse.urljoin(murl, uri)
        mst, mhd, mbody = http_get(purl, timeout=30)
        hls_summary(mst, mhd, mbody, f"media playlist {label}", uid=uid)
        if mst == 200 and mbody and not str(mbody).startswith("<"):
            seg_lines = [l for l in str(mbody).splitlines()
                         if l.strip() and not l.startswith("#")]
            print(f"  segment URIs in media playlist: {len(seg_lines)}")
            for s in seg_lines[:3]:
                print(f"    | {redact_body(s)}")

    if args.deep:
        probe_deep(master, BASE, token, uid, ep["Id"], mid, video, audio)

    print("\nDONE (all output redacted — no tokens above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())