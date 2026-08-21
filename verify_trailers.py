#!/usr/bin/env python3
"""Verify + enrich official YouTube trailer IDs for RKM Watchlist entries.

Keyless method (no TMDB/TVDB keys required):
  1. Existing trailerId -> verify live via YouTube oEmbed (200 + title contains 'trailer').
  2. Dead/missing -> YouTube search ("TITLE YEAR official trailer") -> parse ytInitialData
     -> score candidates (official > teaser > tv spot, channel name match, length) ->
     verify best candidate via oEmbed -> write trailerId + trailerTitle.
  3. NEVER writes an unverified ID. Dead/unfindable -> keeps empty (UI falls back to search link).

Usage:
  python3 verify_trailers.py --list      # show top candidates per title, write nothing
  python3 verify_trailers.py             # verify + fix atomically, then rebuild
"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.parse

WL = "/workspace/media/watchlist.json"
BASE = "/workspace/media/watchlist"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def oembed_verify(video_id):
    """Return (ok, title) for a YouTube video id via oEmbed (authoritative existence check)."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        status, body = http_get(url, timeout=10)
        if status != 200:
            return False, ""
        d = json.loads(body.decode("utf-8", "ignore"))
        return True, d.get("title", "")
    except Exception:
        return False, ""


def yt_candidates(query):
    """Fetch YouTube search results and return candidate dicts."""
    q = urllib.parse.quote(query)
    status, body = http_get(f"https://www.youtube.com/results?search_query={q}", timeout=20)
    if status != 200:
        return []
    html = body.decode("utf-8", "ignore")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    try:
        d = json.loads(m.group(1))
    except Exception:
        return []

    out = []
    def walk(o):
        if isinstance(o, dict):
            if "videoRenderer" in o:
                out.append(o["videoRenderer"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d)
    cands = []
    for i, v in enumerate(out[:30]):
        title = "".join(r.get("text", "") for r in (v.get("title", {}).get("runs") or []))
        vid = v.get("videoId")
        owner = ""
        try:
            owner = (v.get("ownerText", {}).get("runs") or [{}])[0].get("text", "")
        except Exception:
            pass
        dur = v.get("lengthText", {}).get("simpleText", "")
        pub = v.get("publishedTimeText", {}).get("simpleText", "")
        if vid and title:
            cands.append({"pos": i, "id": vid, "title": title, "owner": owner,
                          "dur": dur, "pub": pub})
    return cands


STUDIO_CHANNELS = [
    "warner bros", "searchlight", "paramount", "open road", "roadshow",
    "star studios", "gkids", "crunchyroll", "columbia", "universal pictures",
    "fox searchlight", "20th century", "sony pictures", "lionsgate", "a24",
    "netflix", "amazon studios", "disney", "marvel", "eros", "viacom18",
    "yash raj", "t-series", "zeemusic", "eone", "paradise", "mubi",
]

def score_candidate(c, title_words):
    """Heuristic score: higher = better official-trailer candidate."""
    t = c["title"].lower()
    o = c["owner"].lower()
    score = 20  # base (search relevance already ordered)
    if "trailer" not in t:
        return -100
    if "official trailer" in t:
        score += 15
    elif "official" in t:
        score += 8
    if "teaser" in t:
        score -= 4
    if "tv spot" in t or "clip" in t or "scene" in t:
        score -= 6
    if "trailer 1" in t or "trailer #1" in t:
        score += 3
    # channel name echo of the movie
    for w in title_words:
        if len(w) >= 4 and (w in o or o in w):
            score += 4
            break
    # real studio/distributor channel > aggregator channel
    if any(s in o for s in STUDIO_CHANNELS):
        score += 6
    elif "rotten tomatoes" in o or "movie trailer" in o or "filmisnow" in o or "kinocheck" in o:
        score -= 3
    # title contains full movie name
    if all(w in t for w in title_words if len(w) >= 4):
        score += 6
    # extract duration seconds ~ 90-210s typical for trailers
    m = re.match(r"(\d+):(\d+)", c["dur"])
    if m:
        secs = int(m.group(1)) * 60 + int(m.group(2))
        if 60 <= secs <= 240:
            score += 3
        elif secs > 300:
            score -= 3
    if c["pos"] < 5:
        score += 5 - c["pos"]
    return score


def pick_trailer(title, year, list_only=False):
    """Search and return (trailerId, trailerTitle) or ("", "")."""
    words = [w for w in re.split(r"[^a-z0-9]+", title.lower()) if w]
    query = f"{title} {year} official trailer"
    cands = yt_candidates(query)
    if not cands:
        print(f"    [no candidates for {query}]")
        return "", ""
    scored = sorted(((score_candidate(c, words), c) for c in cands), key=lambda x: -x[0])
    if list_only:
        print(f"  {title} ({year}) — top candidates:")
        for s, c in scored[:5]:
            print(f"    {s:>3}  {c['id']}  {c['title'][:58]}  [{c['owner'][:22]}]  {c['dur']}")
    for s, c in scored:
        if s < 15:
            break
        ok, ot = oembed_verify(c["id"])
        if ok:
            return c["id"], c["title"]
    return "", ""


def main():
    list_only = "--list" in sys.argv
    wl = json.load(open(WL))
    pend = wl.get("pending", [])
    print(f"Titles to process: {len(pend)}\n")

    changed = 0
    for e in pend:
        t = e.get("title", "")
        y = e.get("year", "")
        cur = e.get("trailerId", "")
        verdict = "keep"
        if cur:
            ok, ot = oembed_verify(cur)
            if ok and "trailer" in ot.lower():
                # refresh stale title text if we have richer oembed info
                if ot != e.get("trailerTitle", ""):
                    e["trailerTitle"] = ot
                print(f"  ✓ {t}: keeps {cur} — oembed OK ({ot[:44]})")
                continue
            print(f"  ✗ {t}: CURRENT ID DEAD ({cur}) — searching replacement")
            verdict = "dead"
        tid, ttitle = pick_trailer(t, y, list_only=list_only)
        if tid and (list_only or verdict == "dead" or not cur):
            if list_only:
                continue
            e["trailerId"] = tid
            e["trailerTitle"] = ttitle
            if "trailer" in e and e["trailer"].startswith("https://www.youtube.com/results"):
                e.pop("trailer", None)  # drop stale search-link fallback, now has real embed
            changed += 1
            print(f"  ✓ {t}: NEW {tid} — {ttitle[:54]}")
        elif not tid and not list_only:
            print(f"  - {t}: no verified trailer found (search-link fallback stays)")
        time.sleep(0.5)

    if list_only:
        print("\nList mode — nothing written.")
        return

    if changed:
        wl["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = WL + ".tmp"
        json.dump(wl, open(tmp, "w"), indent=2)
        os.replace(tmp, WL)
        print(f"\nwatchlist.json updated ({changed} fixed) — rebuilding dashboard")
        subprocess.run(["python3", os.path.join(BASE, "build_dashboard.py")], cwd=BASE, timeout=180)
    else:
        print("\nNothing to fix — all IDs verified.")


if __name__ == "__main__":
    main()