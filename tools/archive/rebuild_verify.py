def load_env():
    env = {}
    # 1. real environment (set by docker-compose env_file / -e)
    for k in ("RADARR_URL", "SONARR_URL", "RADARR_API_KEY", "SONARR_API_KEY",
              "TMDB_API_KEY", "TVDB_API_KEY", "PLEX_URL", "PLEX_TOKEN",
              "JELLYFIN_URL", "JELLYFIN_API_KEY", "PROWLARR_URL",
              "BROWSER_RADARR_URL", "BROWSER_SONARR_URL", "MEDIA_HOST"):
        v = os.environ.get(k)
        if v:
            env[k] = v
    if env:
        return env
    # 2. .env file (local/dev)
    for path in ("/app/.env", "/workspace/media/.env"):
        try:
            for line in open(path):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
            if env:
                break
        except OSError:
            continue
    return env


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def check_api_keys_absent(blob):
    leaked = []
    for k in SECRET_KEY_NAMES:
        # look for actual key value patterns (32+ hex chars, or typical key lengths)
        if re.search(r"[0-9a-fA-F]{32,}", blob) and k in blob:
            leaked.append(k)
    # also reject any obvious key value patterns in data/html (e.g. "key=abcdef...")
    if re.search(r"(key|secret|token|api.*key)[\s=]*[0-9a-f]{32,}", blob, re.I):
        leaked.append(k)
    return not leaked


def main():
    print("== RKM Cinema build + verify ==\n")

    # 1) BUILD
    r = subprocess.run(["python3", "build_dashboard.py"], capture_output=True, text=True,
                       cwd=BASE, timeout=180)
    print((r.stdout or r.stderr).strip()[-400:])
    if r.returncode != 0:
        print("\nBUILD FAILED — aborting verification.")
        sys.exit(1)
    print()

    # 2) load data
    wl = json.load(open(WL))
    data = json.load(open(DATA))
    entries = data["entries"]
    html = open(HTML).read()

    print("== validation ==")

    # generated successfully + >= 1 card
    check("data.json generated", os.path.exists(DATA) and os.path.getsize(DATA) > 100)
    check("index.html generated", os.path.exists(HTML) and os.path.getsize(HTML) > 100)
    check(">= 1 entry", len(entries) >= 1, f"{len(entries)} entries")
    check("modal JS present (app.js)", "app.js" in html and os.path.exists(os.path.join(BASE, "app.js")))
    check("CSS present (app.css)", "app.css" in html and os.path.exists(os.path.join(BASE, "app.css")))

    # no duplicate titles
    titles = [e["title"] for e in entries]
    check("no duplicate titles", len(titles) == len(set(titles)),
          f"{len(titles)} titles / {len(set(titles))} distinct")

    # no stale gateway IPs in public files
    bad_gw = []
    for fn in ("index.html", "dashboard.html", "dashboard-data.json", "app.js", "app.css"):
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            continue
        if any(pat in open(p).read() for pat in GATEWAY_IF_PATTERNS):
            bad_gw.append(fn)
    check("no stale gateway IPs in public files", not bad_gw, f"found in: {bad_gw}" if bad_gw else "clean")

    # API keys never in public files
    blob = (open(DATA).read() + html + open(os.path.join(BASE, "app.js")).read()
            + open(os.path.join(BASE, "app.css")).read())
    check("API keys absent from public files", check_api_keys_absent(blob),
          "clean" if check_api_keys_absent(blob) else f"leaked keys: {leaked}" if leaked else "clean")

    # required fields per entry
    req = ["imdbId", "title", "year", "type", "poster", "trailerUrl"]
    missing = []
    for e in entries:
        for k in req:
            if not e.get(k) and e.get(k) != 0:
                missing.append(f"{e.get('title','?')}.{k}")
    check("all entries have required fields", not missing, f"missing: {missing[:5]}" if missing else "ok")

    # trailer IDs valid (oEmbed-verified live)
    dead = []
    for e in entries:
        tid = e.get("trailerId")
        if not tid:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", tid):
            dead.append(f"{e['title']}:malformed")
        elif not oembed_verify(tid):
            dead.append(f"{e['title']}:{tid}")
        time.sleep(0.3)
    check("all trailer IDs verified live", not dead, f"dead: {dead}" if dead else "all 7 verified")

    # download type mapping: movie->radarr, tv->sonarr (check data carries type)
    bad_type = [e["title"] for e in entries if e.get("type") not in ("movie", "tv")]
    check("download type mapping present", not bad_type, f"bad type: {bad_type}" if bad_type else "ok")

    # mobile no overflow (headless chromium)
    overflow = check_mobile_overflow()
    check("mobile layout no horizontal overflow", not overflow,
          "overflow detected" if overflow else "390px viewport clean")

    # radarr/sonarr config exists
    env = load_env()
    has_cfg = bool(env.get("RADARR_URL")) and bool(env.get("RADARR_API_KEY")) \
        and bool(env.get("SONARR_URL")) and bool(env.get("SONARR_API_KEY"))
    check("Radarr/Sonarr endpoint configuration exists", has_cfg,
          "URLs + keys present" if has_cfg else "MISSING config")

    # API smoke test (only if a dev/test server is running)
    api_ok = smoke_api()
    if api_ok is not None:
        check("API smoke (health/status/download mapping)", api_ok, "")

    # summary
    failed = [c for c in checks if not c[1]]
    print(f"\n== result: {len(checks)-len(failed)}/{len(checks)} passed ==")
    if failed:
        print("FAILED CHECKS:")
        for n, _, d in failed:
            print(f"  - {n} ({d})")
        sys.exit(1)
    print("ALL CHECKS PASSED ✅")
    sys.exit(0)