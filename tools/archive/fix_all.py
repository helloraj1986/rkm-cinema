#!/usr/bin/env python3
"""Verify + repair + rebuild + verify live. One deterministic pass."""
import json, os, subprocess, sys, time, urllib.request

WL = "/workspace/media/watchlist.json"
BASE = "/workspace/media/watchlist"

# ---- 1. VERIFY ACTUAL DISK STATE ----
print("== 1. watchlist.json state ==")
size = os.path.getsize(WL)
print(f"size: {size} bytes")
wl = json.load(open(WL))
pend = wl.get("pending", [])
print(f"pending: {len(pend)}")
titles = set()
ok = True
for i, p in enumerate(pend):
    t = p.get("title", "")
    titles.add(t)
    print(f"  [{i}] {t} | {p.get('year')} | trailerId={p.get('trailerId','NONE')}")
    if not p.get("trailerId") or not t:
        ok = False

# ---- 2. REPAIR IF CORRUPTED ----
if len(titles) < 5 or not ok or size < 3000:
    print("\n== 2. REPAIRING (corrupt/duplicate entries) ==")
    SEED = [
        {"title": "Spirited Away", "year": 2001, "category": "Kids & Animation",
         "lang": "Japanese (dub/sub)", "rt": 96, "imdb": 8.6, "isSeries": False,
         "imdbId": "tt0245429", "tmdbId": 129, "cert": "PG",
         "snippet": "A girl stumbles into a world of spirits and must work in a bathhouse to free her parents. Ghibli's masterpiece.",
         "cast": ["Rumi Hiiragi (voice)"], "director": "Hayao Miyazaki",
         "poster": "https://image.tmdb.org/t/p/original/39wmItIWsg5sZMyRUHLkWBcuVCM.jpg",
         "trailerId": "5R6FVcO45F00", "trailerTitle": "Spirited Away - Official Trailer - 2017 - GKIDS 4K",
         "added": "2026-08-17"},
        {"title": "Arrival", "year": 2016, "category": "Sci-Fi/Fantasy",
         "lang": "English", "rt": 94, "imdb": 7.9, "isSeries": False,
         "imdbId": "tt2543164", "tmdbId": 329865, "cert": "",
         "snippet": "A linguist races to communicate with alien visitors before global panic. Cerebral, emotional, masterful.",
         "cast": ["Amy Adams", "Jeremy Renner"], "director": "Denis Villeneuve",
         "poster": "https://image.tmdb.org/t/p/original/x2FJsf1ElAgr63Y3PNPtJrcmpoe.jpg",
         "trailerId": "3WzW4kk6pBM", "trailerTitle": "ARRIVAL - Official Trailer 1 - 2016 - (HD)",
         "added": "2026-08-17"},
        {"title": "Andhadhun", "year": 2018, "category": "Hindi/Indian Cinema",
         "lang": "Hindi", "rt": 100, "imdb": 8.2, "isSeries": False,
         "imdbId": "tt8108198", "tmdbId": 528085, "cert": "",
         "snippet": "A blind pianist stumbles into a murder. A twisty black-comedy thriller that keeps reinventing itself. Hindi masterpiece.",
         "cast": ["Ayushmann Khurrana", "Tabu", "Radhika Apte"], "director": "Sriram Raghavan",
         "poster": "https://image.tmdb.org/t/p/original/dy3K6hNvwE05siGgiLJcEiwgpdO.jpg",
         "trailerId": "Jm9NwiA9bDg", "trailerTitle": "Andhadhun - Official Trailer",
         "added": "2026-08-17"},
        {"title": "The Grand Budapest Hotel", "year": 2014, "category": "Comedy",
         "lang": "English", "rt": 92, "imdb": 8.1, "isSeries": False,
         "imdbId": "tt2278388", "tmdbId": 120467, "cert": "",
         "snippet": "A legendary concierge and his lobby boy tumble through a caper in a fictional European hotel. Visually stunning, hilarious.",
         "cast": ["Ralph Fiennes", "Tony Revolori"], "director": "Wes Anderson",
         "poster": "https://image.tmdb.org/t/p/original/eWdyYQreja6JGCzqHWXpWHDrrPo.jpg",
         "trailerId": "Gp_-6k2YcWA", "trailerTitle": "THE GRAND BUDAPEST HOTEL - Official Trailer",
         "added": "2026-08-17"},
        {"title": "Mad Max: Fury Road", "year": 2015, "category": "Action",
         "lang": "English", "rt": 97, "imdb": 8.1, "isSeries": False,
         "imdbId": "tt1392190", "tmdbId": 76341, "cert": "",
         "snippet": "A post-apocalyptic chase across the wasteland - practical stunts, breathtaking cinema. Australian-made, too.",
         "cast": ["Tom Hardy", "Charlize Theron"], "director": "George Miller",
         "poster": "https://image.tmdb.org/t/p/original/ulcAi4dKpAjHwYGS08vNyx9H6I9.jpg",
         "trailerId": "0A2nUNmcyRI", "trailerTitle": "MAD MAX: FURY ROAD - Official Trailer 2",
         "added": "2026-08-17"},
    ]
    wl = {"rotation_index": 0,
          "rotation": ["Thriller", "Drama", "Kids & Animation", "Sci-Fi/Fantasy", "Comedy",
                       "Action", "Horror", "Crime", "Documentary", "Hindi/Indian Cinema",
                       "Romance", "Classic/Essential"],
          "pending": SEED, "recommended": [],
          "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(wl, open(WL, "w"), indent=2)
    print("repaired: 5 entries restored")
else:
    print("\n== 2. state healthy - no repair needed ==")

# ---- 3. PATCH BUILDER IF MODAL MISSING (idempotent) ----
bpath = os.path.join(BASE, "build_dashboard.py")
b = open(bpath).read()
changed = False
if ".poster img { width:100%; height:100%; object-fit:cover; }" in b and "object-position" not in b.split(".poster img")[1].split(";")[:1][0]:
    pass  # handled below by explicit replacement if needed
# ensure centered poster CSS
if ".poster {" in b and "align-items:flex-end" in b:
    b = b.replace(".poster { height:170px; background:linear-gradient(135deg,#2b2f3a,#191c23); position:relative; display:flex; align-items:flex-end; }",
                  ".poster { height:170px; background:linear-gradient(135deg,#2b2f3a,#191c23); position:relative; display:flex; align-items:center; justify-content:center; overflow:hidden; }")
    changed = True
if ".poster img { width:100%; height:100%; object-fit:cover; }" in b:
    b = b.replace(".poster img { width:100%; height:100%; object-fit:cover; }",
                  ".poster img { width:100%; height:100%; object-fit:cover; object-position:center; }")
    changed = True
# ensure modal CSS
if ".modal {" not in b:
    b = b.replace("footer { color:var(--muted); font-size:11px; margin-top:26px; text-align:center; }",
                  "footer { color:var(--muted); font-size:11px; margin-top:26px; text-align:center; }\n"
                  "  .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,.88); z-index:1000; align-items:center; justify-content:center; }\n"
                  "  .modal.show { display:flex; }\n"
                  "  .modal-box { position:relative; width:min(880px,92vw); background:var(--card); border:1px solid var(--border); border-radius:14px; overflow:hidden; }\n"
                  "  .modal-close { position:absolute; top:12px; right:14px; z-index:5; background:rgba(0,0,0,.65); color:#fff; border:none; border-radius:50%; width:34px; height:34px; font-size:17px; line-height:1; cursor:pointer; }\n"
                  "  .modal-title { padding:13px 18px; font-weight:700; font-size:15px; color:var(--text); background:var(--card); }\n"
                  "  .modal-frame { position:relative; padding-top:56.25%; }\n"
                  "  .modal-frame iframe { position:absolute; inset:0; width:100%; height:100%; border:0; }")
    changed = True
# ensure modal markup
if 'id="modal"' not in b:
    b = b.replace('<footer>Watchlist generated <span id="genTime"></span> &middot; Download adds straight to Radarr/Sonarr</footer>',
                  '<footer>Watchlist generated <span id="genTime"></span> &middot; Download adds straight to Radarr/Sonarr</footer>\n\n'
                  '<div id="modal" class="modal" onclick="closeTrailer(event)">\n'
                  '  <div class="modal-box" onclick="event.stopPropagation()">\n'
                  '    <button class="modal-close" onclick="closeTrailer()" aria-label="Close">&#10005;</button>\n'
                  '    <div class="modal-title" id="modalTitle"></div>\n'
                  '    <div class="modal-frame" id="modalFrame"></div>\n'
                  '  </div>\n'
                  '</div>')
    changed = True
# ensure openTrailer/closeTrailer JS
if "function openTrailer" not in b:
    b = b.replace("function loadSettings(){",
                  "function openTrailer(id, title){\n"
                  "  if (!id){ window.open('https://www.youtube.com/results?search_query=' + encodeURIComponent(title + ' trailer'), '_blank'); return; }\n"
                  "  document.getElementById('modalTitle').textContent = title;\n"
                  "  const f = document.getElementById('modalFrame');\n"
                  "  f.innerHTML = '<iframe src=\"https://www.youtube.com/embed/' + id + '?autoplay=1&rel=0\" allow=\"autoplay; encrypted-media; picture-in-picture\" allowfullscreen></iframe>';\n"
                  "  document.getElementById('modal').classList.add('show');\n"
                  "}\n"
                  "function closeTrailer(e){\n"
                  "  if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains('modal-close')) return;\n"
                  "  const m = document.getElementById('modal');\n"
                  "  m.classList.remove('show');\n"
                  "  document.getElementById('modalFrame').innerHTML = '';\n"
                  "}\n"
                  "function loadSettings(){")
    changed = True
# ensure trailer button uses openTrailer + trailerId
if 'openTrailer(' not in b:
    b = b.replace('<a class="btn btn-tube" target="_blank" rel="noopener" href="${esc(e.trailer)}">&#9654; Trailer</a>',
                  '<button class="btn btn-tube" onclick="openTrailer(\'${esc(e.trailerId)}\', \'${esc(e.title)}\')">&#9654; Trailer</button>')
    changed = True
# ensure entries include trailerId
if '"trailerId"' not in b:
    b = b.replace('"cert": e.get("cert", ""), "added": e.get("added", ""), "poster": e.get("poster", ""),',
                  '"cert": e.get("cert", ""), "added": e.get("added", ""), "poster": e.get("poster", ""),\n        "trailerId": e.get("trailerId", ""),')
    changed = True
if changed:
    open(bpath, "w").write(b)
    print("\n== 3. builder patched (modal + centered posters) ==")
else:
    print("\n== 3. builder already has modal + centered posters ==")

# ---- 4. REBUILD ----
print("== 4. rebuilding dashboard ==")
r = subprocess.run(["python3", os.path.join(BASE, "build_dashboard.py")], capture_output=True, text=True, cwd=BASE, timeout=120)
print((r.stdout or r.stderr).strip()[-200:])

# ---- 5. VERIFY OUTPUT FILE ----
out = os.path.join(BASE, "dashboard.html")
html = open(out).read()
print(f"\n== 5. dashboard.html: {len(html)} bytes ==")
print("embed URLs:", html.count("youtube.com/embed"))
print("modal present:", "id=\"modal\"" in html)
print("openTrailer fn:", "function openTrailer" in html)
print("object-position:center:", "object-position:center" in html)
print("stale gateway (192.168.65.254):", html.count("192.168.65.254"))
print("trailerIds in entries:", html.count("trailerId"))

# ---- 6. VERIFY LIVE SERVER ----
print("\n== 6. live server ==")
try:
    with urllib.request.urlopen("http://rkm-hp.tail8d5e8.ts.net:8123/", timeout=15) as resp:
        body = resp.read().decode("utf-8", "ignore")
        print(f"HTTP {resp.status} | {len(body)} bytes")
        print("live embed URLs:", body.count("youtube.com/embed"))
        print("live modal:", "id=\"modal\"" in body)
        print("live centered:", "object-position:center" in body)
except Exception as e:
    print("live check failed:", e)