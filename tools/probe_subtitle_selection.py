#!/usr/bin/env python3
"""Why is (or isn't) a subtitle row marked as chosen? — read-only diagnosis.

    python3 tools/probe_subtitle_selection.py "3 Deewarein"

Prints, for the exact item:
  * the Jellyfin item id + its subtitle MediaStreams (index/name/language/IsExternal)
  * what the app's /api/library/folders...-adjacent search returns
  * every row the panel would render, with `active` / `local` / `index` / `used_count`
  * playback-info's `preferred_subtitle` (the identity the app applies on load)
  * the on-disk pref record, if the store is reachable

READ-ONLY: it never downloads, selects, attaches or deletes anything.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rkm_common import Jellyfin, app_base, http_json, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _shape(payload) -> str:
    """`ok` or the error marker rkm_common returns instead of raising."""
    if isinstance(payload, dict):
        for k in ("__http_error__", "__error__"):
            if k in payload:
                return f"FAILED ({k}={payload[k]}) {payload.get('body', '')[:200]}"
    return "ok"


def _exact(items, title: str):
    """Only accept an EXACT (case-insensitive) name match, then a year-suffixed one.

    Jellyfin's SearchTerm is a fuzzy ranking: a bare title match has already put a
    resume position on the wrong film in this repo (see the skill's resume notes).
    """
    want = title.strip().lower()
    hits = [i for i in items if (i.get("Name") or "").strip().lower() == want]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        near = ", ".join(f"{i.get('Name')} ({i.get('Id','')[:8]})" for i in items[:8])
        print(f"!! no EXACT match for {title!r}; Jellyfin offered: {near}")
        return None
    print(f"!! {len(hits)} items are named exactly {title!r} — refusing to guess:")
    for i in hits:
        print(f"   {i.get('Id')}  {i.get('Path')}")
    return None


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "3 Deewarein"
    env = load_env(ROOT)
    jf = Jellyfin(env=env)

    users = jf.get("/Users")
    uid = next((u["Id"] for u in users if u.get("Name") == "admin"), users[0]["Id"])
    print(f"jellyfin user: {uid}")

    found = jf.get(f"/Users/{uid}/Items?Recursive=true&IncludeItemTypes=Movie"
                   f"&SearchTerm={quote(title)}&Fields=Path,ProviderIds,MediaStreams&Limit=25")
    item = _exact(found.get("Items", []), title)
    if not item:
        return 2
    item_id = item["Id"]
    print(f"\nitem   : {item_id}\nname   : {item.get('Name')} ({item.get('ProductionYear')})"
          f"\npath   : {item.get('Path')}")
    print(f"tmdb   : {(item.get('ProviderIds') or {}).get('Tmdb')}  "
          f"imdb: {(item.get('ProviderIds') or {}).get('Imdb')}")

    subs = [s for s in (item.get("MediaStreams") or []) if s.get("Type") == "Subtitle"]
    print(f"\nsubtitle tracks the SERVER holds: {len(subs)}")
    for s in subs:
        print(f"  index={s.get('Index')} lang={s.get('Language')} "
              f"external={s.get('IsExternal')} name={s.get('DisplayTitle') or s.get('Title')}")

    api = app_base(env)
    print(f"\napp api: {api}")
    search = http_json(f"{api}/api/jellyfin/subtitle-search?id={item_id}&language=en",
                       timeout=60)
    print(f"\n/subtitle-search -> {_shape(search)}")
    if isinstance(search, dict):
        print(f"  enabled={search.get('enabled')} disabled={search.get('disabled')} "
              f"warning={search.get('warning')!r} remaining={search.get('remaining_downloads')}")
        rows = search.get("results") or []
        print(f"  {len(rows)} rows as the panel receives them:")
        for r in rows[:14]:
            mark = "*ACTIVE*" if r.get("active") else "        "
            print(f"   {mark} local={str(r.get('local')):5} index={str(r.get('index')):4} "
                  f"used={r.get('used_count')} id={r.get('subtitle_id') or '-'} "
                  f"{r.get('display_title')}")
        print(f"  preferred_subtitle: {json.dumps(search.get('preferred_subtitle'))}")

    info = http_json(f"{api}/api/jellyfin/playback-info?id={item_id}", timeout=60)
    print(f"\n/playback-info -> {_shape(info)}")
    if isinstance(info, dict):
        print(f"  preferred_subtitle: {json.dumps(info.get('preferred_subtitle'))}")
        for t in (info.get("subtitles") or []):
            print(f"  track index={t.get('index')} lang={t.get('language')} name={t.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
