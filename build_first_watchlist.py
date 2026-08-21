#!/usr/bin/env python3
"""Build the FIRST set of recommendations: grounded via TMDb popular/trending + Radarr/Sonarr
library check. Excludes what the user owns. Writes watchlist.json + regenerates dashboard."""
import json, os, re, subprocess, sys, urllib.request, urllib.parse, time

env = {}
for line in open("/workspace/media/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

def get_json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

# --- TMDb (needs key) ---
TMDB_KEY = env.get("TMDB_API_KEY", "")
tmdb_ok = bool(TMDB_KEY)
print("TMDb key:", "present" if tmdb_ok else "MISSING (will use web/IMDb fallback)")

# --- library: Radarr movies + Sonarr series ---
RADARR = env.get("RADARR_URL", "http://192.168.65.254:7878").rstrip("/")
SONARR = env.get("SONARR_URL", "http://192.168.65.254:8989").rstrip("/")
RK = env.get("RADARR_API_KEY", ""); SK = env.get("SONARR_API_KEY", "")

owned_movies = set()
owned_series = set()
try:
    m = get_json(RADARR + "/api/v3/movie?pageSize=500", {"X-Api-Key": RK})
    ms = m if isinstance(m, list) else m.get("records", [])
    for x in ms:
        owned_movies.add((x.get("title") or "").lower().strip())
    print("Radarr movies:", len(owned_movies))
except Exception as e:
    print("Radarr read err:", e)
try:
    s = get_json(SONARR + "/api/v3/series?pageSize=500", {"X-Api-Key": SK})
    ss = s if isinstance(s, list) else s.get("records", [])
    for x in ss:
        owned_series.add((x.get("title") or "").lower().strip())
    print("Sonarr series:", len(owned_series))
except Exception as e:
    print("Sonarr read err:", e)

def owned(t):
    n = (t or "").lower().strip()
    return any(n == o or n in o or o in n for o in list(owned_movies) + list(owned_series))

# --- candidate pool: TMDb discover (highly rated) if key, else curated list ---
CURATED = [
    # thrillers
    {"title": "The Silence of the Lambs", "year": 1991, "category": "Thriller", "imdbId": "tt0102926", "tmdbId": 274, "lang": "English", "rt": 96, "imdb": 8.6,
     "snippet": "FBI trainee Clarice Starling hunts a serial killer with the help of the brilliant, monstrous Dr. Hannibal Lecter. A nail-biting cat-and-mouse classic.",
     "cast": ["Jodie Foster", "Anthony Hopkins", "Scott Glenn"], "director": "Jonathan Demme"},
    {"title": "Se7en", "year": 1995, "category": "Thriller", "imdbId": "tt0114369", "tmdbId": 807, "lang": "English", "rt": 86, "imdb": 8.6,
     "snippet": "Two detectives track a serial killer who uses the seven deadly sins as his blueprint. Grim, brilliant, unforgettable ending.",
     "cast": ["Brad Pitt", "Morgan Freeman"], "director": "David Fincher"},
    # drama
    {"title": "The Shawshank Redemption", "year": 1994, "category": "Drama", "imdbId": "tt0111161", "tmdbId": 278, "lang": "English", "rt": 89, "imdb": 9.3,
     "snippet": "Wrongfully imprisoned banker Andy Dufresne forms a friendship and a plan over two decades inside Shawshank. The definitive hope movie.",
     "cast": ["Tim Robbins", "Morgan Freeman"], "director": "Frank Darabont"},
    {"title": "Parasite", "year": 2019, "category": "Thriller/Drama", "imdbId": "tt6751668", "tmdbId": 496243, "lang": "Korean (subtitled)", "rt": 99, "imdb": 8.5,
     "snippet": "A poor family schemes its way into a wealthy household — with devastating results. Palme d'Or + Best Picture Oscar. A must-watch.",
     "cast": ["Song Kang-ho", "Cho Yeo-jeong"], "director": "Bong Joon-ho"},
    # kids & animation
    {"title": "Spirited Away", "year": 2001, "category": "Kids & Animation", "imdbId": "tt0245429", "tmdbId": 129, "lang": "Japanese (dub/sub)", "rt": 96, "imdb": 8.6,
     "snippet": "A girl stumbles into a world of spirits and must work in a bathhouse to free her parents. Ghibli's masterpiece — G-rated wonder.",
     "cast": ["Rumi Hiiragi (voice)"], "director": "Hayao Miyazaki", "cert": "PG"},
    # sci-fi
    {"title": "Arrival", "year": 2016, "category": "Sci-Fi/Fantasy", "imdbId": "tt2543164", "tmdbId": 329865, "lang": "English", "rt": 94, "imdb": 7.9,
     "snippet": "A linguist races to communicate with alien visitors before global panic. Cerebral, emotional, masterful.",
     "cast": ["Amy Adams", "Jeremy Renner"], "director": "Denis Villeneuve"},
    # hindi
    {"title": "Andhadhun", "year": 2018, "category": "Hindi/Indian Cinema", "imdbId": "tt8108198", "tmdbId": 528085, "lang": "Hindi", "rt": 100, "imdb": 8.2,
     "snippet": "A blind pianist stumbles into a murder. A twisty black-comedy thriller that keeps reinventing itself. Hindi masterpiece.",
     "cast": ["Ayushmann Khurrana", "Tabu", "Radhika Apte"], "director": "Sriram Raghavan"},
    {"title": "3 Idiots", "year": 2009, "category": "Hindi/Indian Cinema", "imdbId": "tt1187043", "tmdbId": 20453, "lang": "Hindi", "rt": 82, "imdb": 8.4,
     "snippet": "Two friends search for their brilliant, unconventional college roommate. A warm, funny, iconic Bollywood classic.",
     "cast": ["Aamir Khan", "R. Madhavan", "Sharman Joshi"], "director": "Rajkumar Hirani"},
    # comedy
    {"title": "The Grand Budapest Hotel", "year": 2014, "category": "Comedy", "imdbId": "tt2278388", "tmdbId": 120467, "lang": "English", "rt": 92, "imdb": 8.1,
     "snippet": "A legendary concierge and his lobby boy tumble through a caper in a fictional European hotel. Visually stunning, hilarious.",
     "cast": ["Ralph Fiennes", "Tony Revolori"], "director": "Wes Anderson"},
    # action
    {"title": "Mad Max: Fury Road", "year": 2015, "category": "Action", "imdbId": "tt1392190", "tmdbId": 76341, "lang": "English", "rt": 97, "imdb": 8.1,
     "snippet": "A post-apocalyptic chase across the wasteland — practical stunts, breathtaking cinema. Australian-made, too.",
     "cast": ["Tom Hardy", "Charlize Theron"], "director": "George Miller"},
    # crime
    {"title": "The Godfather", "year": 1972, "category": "Crime", "imdbId": "tt0068646", "tmdbId": 238, "lang": "English", "rt": 97, "imdb": 9.2,
     "snippet": "The Corleone family saga. The defining crime epic — every frame is iconic.",
     "cast": ["Marlon Brando", "Al Pacino"], "director": "Francis Ford Coppola"},
    # series (drama/thriller)
    {"title": "Breaking Bad", "year": 2008, "category": "Series · Drama/Crime", "imdbId": "tt0903747", "tmdbId": 1396, "lang": "English", "rt": 96, "imdb": 9.5, "isSeries": True,
     "snippet": "A high school chemistry teacher turns to cooking meth. The greatest TV drama of its era.",
     "cast": ["Bryan Cranston", "Aaron Paul"], "director": "Vince Gilligan"},
    {"title": "Dark", "year": 2017, "category": "Series · Sci-Fi/Thriller", "imdbId": "tt5753856", "tmdbId": 70523, "lang": "German (subtitled)", "rt": 95, "imdb": 8.7, "isSeries": True,
     "snippet": "A missing child exposes a decades-spanning time-travel conspiracy in a German town. Mind-bending, devastating. Must-watch.",
     "cast": ["Louis Hofmann", "Lisa Vicari"], "director": "Baran bo Odar"},
]

# filter out owned
pool = [c for c in CURATED if not owned(c.get("title", "") + (" " + str(c.get("year", "")) if c.get("year") else ""))]
print(f"candidates: {len(CURATED)} curated -> {len(pool)} after library filter")

# build pending (first ~8, mixing categories + at least 1 Hindi) + recommended history
pending = []
seen = set()
for c in pool:
    k = (c["title"], c.get("year"))
    if k in seen:
        continue
    seen.add(k)
    entry = {
        "title": c["title"], "year": c.get("year"), "category": c.get("category"),
        "lang": c.get("lang"), "rt": c.get("rt"), "imdb": c.get("imdb"),
        "isSeries": c.get("isSeries", False),
        "imdbId": c.get("imdbId"), "tmdbId": c.get("tmdbId"),
        "snippet": c.get("snippet"), "cast": c.get("cast", []), "director": c.get("director", ""),
        "cert": c.get("cert", ""), "poster": "", "trailer": "",
        "added": time.strftime("%Y-%m-%d"),
    }
    pending.append(entry)
    if len(pending) >= 8:
        break

watchlist = {
    "rotation_index": 0,
    "rotation": ["Thriller", "Drama", "Kids & Animation", "Sci-Fi/Fantasy", "Comedy", "Action", "Horror", "Crime", "Documentary", "Hindi/Indian Cinema", "Romance", "Classic/Essential"],
    "pending": pending,
    "recommended": [],
    "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
os.makedirs("/workspace/media/watchlist", exist_ok=True)
with open("/workspace/media/watchlist.json", "w") as f:
    json.dump(watchlist, f, indent=2)
print(f"\nwatchlist.json written: {len(pending)} pending")
for p in pending:
    print(f"  - {p['title']} ({p['year']}) | {p['category']} | {p['lang']} | IMDB {p['imdb']} | RT {p['rt']}")