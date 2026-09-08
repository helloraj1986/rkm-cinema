"""Phase 1 probe: Jellyfin item-detail shape (docs/PLEX_UI_PLAN.md §3).

Authenticates against the bundled Jellyfin (admin creds from the project
.env), fetches a real Movie/Series item with the full detail Fields list, and
reports:

- the raw metadata keys the normaliser maps (Overview / Genres /
  CommunityRating / OfficialRating / Studios / People / ImageTags /
  BackdropImageTags / PrimaryImageAspectRatio / UserData / RunTimeTicks);
- the People entry shape (Type / Role / PrimaryImageTag) and a per-Type
  count, so the actor/director/writer grouping matches reality;
- the person-image endpoint shape: ``/Items/{personId}/Images/Primary``
  (status + content-type + byte length) — confirms the poster proxy pattern
  serves headshots unchanged;
- the Episode item shape (SeriesId/SeriesName/SeasonId/IndexNumber) when a
  series exists in the library.

Output is REDACTED — tokens/URLs never printed. Run from the repo root:

    python3 scripts/probe_jellyfin_detail.py [--limit N]

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
    'DeviceId="rkm-detail-probe-01", Version="1.0"'
)

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

DETAIL_FIELDS = (
    "Overview,Genres,People,CommunityRating,CriticRating,OfficialRating,"
    "Studios,Taglines,ProviderIds,ProductionYear,RunTimeTicks,UserData,"
    "PrimaryImageAspectRatio,ImageTags,BackdropImageTags,MediaSources,"
    "SeriesId,SeriesName,SeasonId,SeasonName,IndexNumber,ParentIndexNumber"
)


def _load_env() -> dict[str, str]:
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


def redact_url(url: str) -> str:
    return re.sub(r"api_key=[^&\s\"']+", "api_key=<redacted>", url)


def http_get_json(url: str, *, timeout: int = 20):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200)), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return int(e.code), json.loads(e.read().decode("utf-8", errors="replace") or "{}")


def http_get_bytes(url: str, *, timeout: int = 20):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (int(getattr(r, "status", 200)),
                    r.headers.get("Content-Type", ""),
                    len(r.read()))
    except urllib.error.HTTPError as e:
        return int(e.code), e.headers.get("Content-Type", ""), 0


def fmt_people(people: list) -> None:
    if not people:
        print("  People: (none)")
        return
    by_type: dict[str, int] = {}
    first: dict[str, dict] = {}
    for p in people:
        t = str(p.get("Type") or "?")
        by_type[t] = by_type.get(t, 0) + 1
        first.setdefault(t, p)
    print(f"  People: {len(people)} entries  {by_type}")
    for t, p in first.items():
        keys = sorted(p.keys())
        img = "PrimaryImageTag" in keys
        print(f"    {t}: Id={p.get('Id')} Name={p.get('Name')!r} "
              f"Role={p.get('Role')!r} PrimaryImageTag={img} keys={keys}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3, help="max items per type to probe")
    args = ap.parse_args()

    env = _load_env()
    user = os.environ.get("RKM_JELLYFIN_ADMIN_USER") or env.get("RKM_JELLYFIN_ADMIN_USER")
    pw = os.environ.get("RKM_JELLYFIN_ADMIN_PASSWORD") or env.get("RKM_JELLYFIN_ADMIN_PASSWORD")
    if not (user and pw):
        print("ERROR: need RKM_JELLYFIN_ADMIN_USER/PASSWORD in project .env or env", file=sys.stderr)
        return 2

    # --- auth ---------------------------------------------------------------
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"{BASE}/Users/AuthenticateByName",
                data=json.dumps({"Username": user, "Pw": pw}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json",
                         "X-Emby-Authorization": AUTH_HEADER}), timeout=15) as r:
            auth = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"auth failed: {e}", file=sys.stderr)
        return 1
    token = auth["AccessToken"]
    uid = auth["User"]["Id"]
    print(f"authenticated user={auth['User'].get('Name')} (token redacted)")

    q = lambda **kw: "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in kw.items())

    # A person WITH a PrimaryImageTag (Jellyfin confirms it has a headshot) is
    # the right probe target — people without one 404 on the image endpoint.
    imaged_person: str | None = None
    imaged_person_name: str = ""
    for itype in ("Movie", "Series"):
        items_url = (f"{BASE}/Users/{uid}/Items?Recursive=true"
                     f"&IncludeItemTypes={itype}&Limit={args.limit}"
                     f"&Fields={DETAIL_FIELDS}&{q(**{'api_key': token})}")
        st, d = http_get_json(items_url)
        items = d.get("Items") or []
        print(f"\n=== {itype}s found: {len(items)} ===")
        for it in items:
            iid = it.get("Id")
            print(f"\n-- {itype} '{it.get('Name')}' ({it.get('ProductionYear')}) id={iid}")
            print(f"   RunTimeTicks={it.get('RunTimeTicks')} "
                  f"OfficialRating={it.get('OfficialRating')!r} "
                  f"CommunityRating={it.get('CommunityRating')}")
            print(f"   Overview: {(it.get('Overview') or '')[:120]!r}...")
            print(f"   Genres={it.get('Genres')}")
            print(f"   Studios={[s.get('Name') for s in (it.get('Studios') or [])]}")
            itags = it.get("ImageTags") or {}
            print(f"   ImageTags keys={sorted(itags.keys())} "
                  f"BackdropImageTags={it.get('BackdropImageTags')} "
                  f"PrimaryImageAspectRatio={it.get('PrimaryImageAspectRatio')}")
            ud = it.get("UserData") or {}
            print(f"   UserData keys={sorted(ud.keys())} "
                  f"Played={ud.get('Played')} PlayCount={ud.get('PlayCount')}")
            fmt_people(it.get("People") or [])
            if itype == "Series":
                print(f"   Series extras: SeasonCount? n/a (list via episodes endpoint)")
            if imaged_person is None:
                for p in (it.get("People") or []):
                    if p.get("Id") and p.get("PrimaryImageTag"):
                        imaged_person = p["Id"]
                        imaged_person_name = str(p.get("Name") or "")
                        break
            # --- episode-context item: probe first episode if any
            if itype == "Series":
                eps_url = (f"{BASE}/Users/{uid}/Items?ParentId={iid}"
                           f"&IncludeItemTypes=Episode&Recursive=true&Limit=1"
                           f"&Fields={DETAIL_FIELDS}&{q(**{'api_key': token})}")
                est, ed = http_get_json(eps_url)
                eps = ed.get("Items") or []
                if eps:
                    e0 = eps[0]
                    print(f"   episode sample '{e0.get('Name')}': SeriesId={e0.get('SeriesId')} "
                          f"SeriesName={e0.get('SeriesName')!r} SeasonId={e0.get('SeasonId')} "
                          f"S{e0.get('ParentIndexNumber')}E{e0.get('IndexNumber')} "
                          f"RunTimeTicks={e0.get('RunTimeTicks')}")

    # --- single-item endpoint shape (what the provider will call) -----------
    print("\n=== single-item detail endpoint (Users/{uid}/Items/{id}) ===")
    single_ids = []
    for itype in ("Movie", "Series"):
        items_url = (f"{BASE}/Users/{uid}/Items?Recursive=true"
                     f"&IncludeItemTypes={itype}&Limit=1"
                     f"&Fields={DETAIL_FIELDS}&{q(**{'api_key': token})}")
        _, d = http_get_json(items_url)
        items = d.get("Items") or []
        if items:
            single_ids.append((itype, items[0].get("Id"), items[0].get("Name")))
    for itype, iid, iname in single_ids[:2]:
        det_url = (f"{BASE}/Users/{uid}/Items/{iid}"
                   f"?Fields={DETAIL_FIELDS}&{q(**{'api_key': token})}")
        st, det = http_get_json(det_url)
        people = det.get("People") or []
        print(f"{itype} '{iname}': HTTP {st} Name={det.get('Name')!r} "
              f"People={len(people)} OverviewPresent={bool(det.get('Overview'))} "
              f"Genres={len(det.get('Genres') or [])} "
              f"Studios={[s.get('Name') for s in (det.get('Studios') or [])]} "
              f"OfficialRating={det.get('OfficialRating')!r} "
              f"CommunityRating={det.get('CommunityRating')} "
              f"BackdropTags={len(det.get('BackdropImageTags') or [])}")

    # --- person-image probe -------------------------------------------------
    print("\n=== person-image probe ===")
    if not imaged_person:
        print("no imaged People found to probe")
    else:
        purl = (f"{BASE}/Items/{imaged_person}/Images/Primary"
                f"?{q(**{'api_key': token})}")
        pst, pct, plen = http_get_bytes(purl)
        print(f"GET /Items/<person:{imaged_person_name}>/Images/Primary -> HTTP {pst} "
              f"Content-Type={pct!r} bytes={plen} (person id redacted)")
        # With maxWidth + quality like the poster proxy sends.
        purl2 = (f"{BASE}/Items/{imaged_person}/Images/Primary"
                 f"?{q(**{'api_key': token, 'maxWidth': 300, 'quality': 90})}")
        pst2, pct2, plen2 = http_get_bytes(purl2)
        print(f"  +maxWidth=300&quality=90 -> HTTP {pst2} Content-Type={pct2!r} bytes={plen2}")

    print("\nDONE (all output redacted — no tokens above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
