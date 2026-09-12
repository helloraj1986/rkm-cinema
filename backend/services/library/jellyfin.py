"""Jellyfin library provider.

Implements the :class:`LibraryProvider` interface for Jellyfin (the bundled,
self-contained media server). The API shape is Emby-derived — Jellyfin forked
Emby and keeps ``/Items``, ``/System/Info/Public`` and the
``Imdb``/``Tmdb``/``Tvdb`` provider ids — so the header and endpoint naming
follow Emby's, which is Jellyfin's own protocol, not a second backend. This module
is the single home for Jellyfin item matching, item-id / server-id resolution
and deep-link building — no other code path reverses Jellyfin's URL format.

Availability only — per-episode *watched / progress* state is a separate,
later capability (experiment Appendix A Phase 1); this provider answers "is
the movie/series in the library at all".
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from services.library.service import LibraryProvider, LibraryMatch

logger = logging.getLogger("rkm.library.jellyfin")


class JellyfinItem:
    """A single item in the Jellyfin library (provider model)."""

    def __init__(self, name: str, year: int, id: str, thumb: str = "",
                 is_series: bool = False, provider_ids: Optional[dict] = None,
                 user_data: Optional[dict] = None,
                 played: bool = False, position_ticks: int = 0,
                 runtime_ticks: int = 0, play_count: int = 0,
                 last_played: str = "",
                 genres: Optional[list] = None, date_added: str = ""):
        self.name = name
        self.year = year
        self.id = id
        self.thumb = thumb
        self.is_series = is_series
        self.provider_ids = provider_ids or {}
        self.user_data = user_data or {}
        # Playback facts (UserData + RunTimeTicks) — drives watched/progress UI.
        self.played = played
        self.position_ticks = position_ticks
        self.runtime_ticks = runtime_ticks
        # Extra watch-state facts (roadmap item 2) — play count + last-played date.
        self.play_count = play_count
        self.last_played = last_played
        # Discovery facts (roadmap item 4) — genre names + DateCreated (ISO).
        self.genres = [str(g) for g in (genres or [])]
        self.date_added = date_added or ""

    def matches(self, name: str, year: Optional[int] = None) -> bool:
        search_lower = name.lower()
        item_lower = self.name.lower()
        if search_lower not in item_lower and item_lower not in search_lower:
            return False
        if year is not None and self.year != year:
            return False
        return True


class JellyfinLibraryProvider(LibraryProvider):
    """Provider interface over a Jellyfin library."""

    name = "jellyfin"

    #: How long a full library scan is considered fresh (spec §29: a 60s window).
    JELLYFIN_SCAN_TTL = 60

    def __init__(self, *, config=None, http=None, tmdb=None):
        from config.settings import get_config
        self.config = config if config is not None else get_config()
        self.http = http
        self._tmdb_service = tmdb  # injected TMDB client (tests); lazy default
        self._item_cache: Optional[dict] = None      # {"Movie": [...], "Series": [...]}
        self._item_cache_expiry: dict = {}           # per-type expiry (item_type -> epoch)
        self._folders_cache: Optional[list] = None   # library_folders() result
        self._folders_expiry: float = 0              # epoch
        self._server_id_value: str = ""
        self._user_id_value: str = ""
        #: Why the most recent account-management call failed (see last_api_error).
        self._last_api_error: Optional[dict] = None

    #: Fields the single-item detail fetch requests (Plex-style preplay data).
    #: Verified live on Jellyfin 10.11.11 — the single-item endpoint embeds
    #: Overview/Genres/People/Studios/ratings/backdrop tags with these.
    DETAIL_FIELDS = (
        "Overview,Genres,People,CommunityRating,CriticRating,OfficialRating,"
        "Studios,Taglines,ProviderIds,ProductionYear,RunTimeTicks,UserData,"
        "PrimaryImageAspectRatio,ImageTags,BackdropImageTags,MediaSources,"
        "SeriesId,SeriesName,SeasonId,SeasonName,IndexNumber,ParentIndexNumber"
    )

    # ------------------------------------------------------------- LibraryProvider
    def health(self) -> bool:
        try:
            self._get_items("Movie")
            return True
        except Exception:
            return False

    def _configured(self) -> bool:
        return bool(self.config.JELLYFIN_URL and self.config.JELLYFIN_API_KEY)

    def find(self, identity, *, title: str = "", year: Optional[int] = None) -> Optional[LibraryMatch]:
        if not self._configured():
            return None
        itype = "Series" if identity.media_type.value == "tv" else "Movie"
        items = self._get_items(itype)

        # 1. Stable provider-id match (Imdb/Tmdb/Tvdb embedded in the item).
        for item in items:
            pids = getattr(item, "provider_ids", {}) or {}
            if identity.imdb_id and pids.get("imdb") == identity.imdb_id:
                return self._match_from(item)
            if identity.tmdb_id is not None and pids.get("tmdb") == identity.tmdb_id:
                return self._match_from(item)
            if identity.tvdb_id is not None and pids.get("tvdb") == identity.tvdb_id:
                return self._match_from(item)

        # 2. Title/year fallback.
        if title:
            for item in items:
                if item.matches(title, year):
                    return self._match_from(item)
        return None

    def _match_from(self, item: JellyfinItem) -> LibraryMatch:
        return LibraryMatch(
            provider=self.name,
            provider_item_id=str(item.id),
            title=item.name,
            year=int(item.year) if item.year else None,
            metadata={
                "item_id": str(item.id),
                "server_id": self._server_id(),
                "thumb": item.thumb,
                "provider_ids": dict(getattr(item, "provider_ids", {}) or {}),
                "user_data": dict(getattr(item, "user_data", {}) or {}),
                # Playback facts (seconds) for watched/progress UI.
                "played": bool(getattr(item, "played", False)),
                "playback_position": self._ticks_to_sec(getattr(item, "position_ticks", 0)),
                "runtime": self._ticks_to_sec(getattr(item, "runtime_ticks", 0)),
            },
        )

    @staticmethod
    def _ticks_to_sec(ticks) -> int:
        """Jellyfin time values are in 10ms ticks; seconds = ticks / 1e7."""
        try:
            return max(0, int(int(ticks) // 10_000_000))
        except (TypeError, ValueError):
            return 0

    def recently_added(self, limit: int = 8) -> list[dict]:
        out = []
        for itype in ("Series", "Movie"):
            for item in self._get_items(itype)[:limit]:
                out.append(self._item_public(item))
        return out

    def all_items(self, limit: Optional[int] = None) -> list[dict]:
        """Every Movie + Series in the library (poster-wall grid)."""
        out = []
        for itype in ("Movie", "Series"):
            for item in self._get_items(itype):
                out.append(self._item_public(item))
                if limit and len(out) >= limit:
                    return out
        return out

    # ------------------------------------------------- configurable libraries
    # MEDIA_LIBRARIES_PLAN Phase 2: the server's OWN library folders (Virtual
    # Folders) are the source of truth for configured MEDIA_LIBRARY_N_PATH.
    # Live-verified 2026-09-10 on Jellyfin 10.11 — /Library/VirtualFolders
    # (admin) returns [{Name, CollectionType, Locations, ItemId,
    # PrimaryImageItemId}]; a folder's titles come from /Users/{uid}/Items with
    # ParentId=<folder ItemId>&Recursive=true&IncludeItemTypes=Movie,Series.
    def library_folders(self) -> list[dict]:
        """The media folders **this identity** may see, as display rows.

        ``[{id, name, collection_type, path, locations}]`` where ``id`` is the folder ItemId (the
        ParentId scope used by :meth:`items_in_folder`), ``path`` is the first location and
        ``locations`` every reported one.

        **Phase C (plan §4d):** the two identities are answered by two different server calls, and
        the difference is a platform fact, not a preference — ``/Library/VirtualFolders`` needs
        elevation and answers **403** to a profile's token, so:

        * **somebody else's profile selected** ⇒ that profile's own ``/UserViews?userId=``, i.e.
          the server's GRANT list. Those rows carry no ``CollectionType`` and only a
          Jellyfin-internal path, so each is enriched from the administrator's folder list (display
          metadata the app already holds — it is what ``MEDIA_LIBRARY_N_PATH`` is matched against)
          and then **filtered down to the views**, so nothing an ungranted library says is
          returned.
        * **the administrator's own profile, or no session at all** ⇒ ``/Library/VirtualFolders``
          exactly as before (that call IS elevated for the administrator's own session token —
          measured). Every tool, the provisioner and the bootstrap take this path.
        """
        from api.session import current_session
        context = current_session()
        if context is not None and not context.on_own_profile():
            return self._profile_folders(context.profile_id())
        return self._server_folders()

    def _server_folders(self) -> list[dict]:
        """Every media folder on the server (Jellyfin ``/Library/VirtualFolders``).

        Administrator-level metadata: it lists folders this person may not be allowed to watch,
        which is why the caller filters it down to a profile's own views before returning anything
        (:meth:`library_folders`). Uses the ADMINISTRATOR's credential — the folder list itself is
        never what grants access, so reading it changes nothing about who may watch what.
        """
        import time
        now = time.time()
        if self._folders_cache is not None and now < self._folders_expiry:
            return self._folders_cache
        if not self._configured():
            return []
        from api.session import owner_media_token
        url = (f"{self.config.JELLYFIN_URL}/Library/VirtualFolders"
               f"?api_key={owner_media_token(self.config)}")
        try:
            raw = self._fetch_list_or_items(url)
        except Exception as e:
            logger.warning("Jellyfin library_folders failed: %s", e)
            return []
        rows = []
        for vf in raw:
            vf_id = str(vf.get("ItemId") or "")
            if not vf_id:
                continue
            locations = [str(p) for p in (vf.get("Locations") or []) if str(p or "").strip()]
            if not locations:
                continue
            rows.append({
                "id": vf_id,
                "name": str(vf.get("Name") or ""),
                "collection_type": str(vf.get("CollectionType") or ""),
                "path": locations[0],
                "locations": locations,
            })
        self._folders_cache = rows
        self._folders_expiry = now + self.JELLYFIN_SCAN_TTL
        return rows

    def _profile_folders(self, user_id: str) -> list[dict]:
        """The libraries ONE PROFILE may see — its own ``/UserViews``, enriched for display.

        Not cached: the provider is built per request, and a cache keyed by anything less than the
        user id would be a cross-profile leak waiting to happen.
        """
        if not self._configured() or not user_id:
            return []
        url = (f"{self.config.JELLYFIN_URL}/UserViews"
               f"?userId={urllib.parse.quote(str(user_id))}"
               f"&api_key={self._api_token()}")
        try:
            views = self._fetch_list_or_items(url)
        except Exception as e:
            logger.warning("Jellyfin UserViews(%s) failed: %s", user_id, e)
            return []
        known = {str(f.get("id") or ""): f for f in self._server_folders()}
        rows = []
        for view in views:
            view_id = str(view.get("Id") or "")
            if not view_id:
                continue
            meta = known.get(view_id) or {}
            rows.append({
                "id": view_id,
                "name": str(view.get("Name") or meta.get("name") or ""),
                "collection_type": str(meta.get("collection_type")
                                       or view.get("CollectionType") or ""),
                "path": str(meta.get("path") or ""),
                "locations": list(meta.get("locations") or []),
            })
        return rows

    def items_in_folder(self, folder_id: str, limit: Optional[int] = None) -> list[dict]:
        """Every Movie + Series inside ONE server library folder.

        Folder-scoped via ``ParentId=<folder ItemId>`` (live-verified). Rows use
        the same public item shape as :meth:`all_items`, so existing cards /
        toolbar / player wiring reuse unchanged.
        """
        if not self._configured() or not folder_id:
            return []
        user_id = self._user_id()
        if not user_id:
            return []
        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self._api_token()}"
               f"&ParentId={urllib.parse.quote(str(folder_id))}&Recursive=true"
               f"&IncludeItemTypes=Movie,Series"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,Genres,DateCreated")
        try:
            raw = self._fetch_raw(url)
        except Exception as e:
            logger.warning("Jellyfin items_in_folder(%s) failed: %s", folder_id, e)
            return []
        out = []
        for it in raw:
            typ = str(it.get("Type") or "")
            if typ not in ("Movie", "Series"):
                continue
            item = self._parse_item(it, typ)
            out.append(self._item_public(item))
            if limit and len(out) >= limit:
                break
        return out

    def continue_watching(self, limit: int = 12) -> list[dict]:
        """In-progress titles — movies, series AND episodes.

        Primary source: Jellyfin's ``/Users/{uid}/Items/Resume``, which lists
        every genuinely in-progress item INDIVIDUALLY — including EPISODES
        (series-level UserData does NOT roll up episode positions, so the old
        scan filter could never surface a half-watched episode). Merge = resume
        rows first (server order), then the old scan filter (position>0 and not
        played over Movies+Series) as a fallback for anything Resume missed;
        dedupe by id. Rows carry an additive ``kind`` (movie|show|episode);
        episode rows add an ``episode`` facet ``{number, season, series_id,
        series_name}``. Option A (CONTINUE_WATCHING_EPISODES_PLAN): the
        endpoint stays free-form — no contract change.
        """
        out: list[dict] = []
        seen: set[str] = set()
        resume = self._resume_rows()  # None when the endpoint is unavailable
        for row in resume or []:
            out.append(row)
            seen.add(str(row["item_id"]))
            if len(out) >= limit:
                return out[:limit]
        if len(out) < limit:
            for itype in ("Movie", "Series"):
                for item in self._get_items(itype):
                    if item.played or item.position_ticks <= 0:
                        continue
                    row = self._item_public(item)
                    row["kind"] = "show" if itype == "Series" else "movie"
                    if str(row["item_id"]) in seen:
                        continue
                    seen.add(str(row["item_id"]))
                    out.append(row)
                    if len(out) >= limit:
                        return out[:limit]
        return out[:limit]

    def _resume_rows(self) -> Optional[list[dict]]:
        """In-progress rows straight from Jellyfin's Resume endpoint.

        Returns rows for Movie/Series/Episode Resume entries (episodes carry a
        ``kind: episode`` + the ``episode`` facet), or ``None`` when the
        endpoint can't be reached (caller falls back to the scan filter).
        """
        if not self._configured():
            return None
        uid = self._user_id()
        if not uid:
            return None
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/Resume"
               f"?api_key={self._api_token()}&Limit=100"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,"
               f"UserData,Genres,DateCreated,SeriesId,SeriesName,SeasonId,"
               f"IndexNumber,ParentIndexNumber")
        try:
            raw = self._fetch_raw(url)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin Resume fetch failed: %s", e)
            return None
        out = []
        for it in raw:
            typ = str(it.get("Type") or "")
            if typ == "Episode":
                row = self._episode_resume_public(it)
                if row is not None and not row["played"]:
                    out.append(row)
            elif typ in ("Movie", "Series"):
                row = self._item_public(self._parse_item(it, typ))
                row["kind"] = "show" if typ == "Series" else "movie"
                out.append(row)
        return out

    def _episode_resume_public(self, it: dict) -> Optional[dict]:
        """One Resume episode → the public item shape (with its episode facet).

        Episode Resume entries list individually with their own ``UserData``
        (position/runtime) + series context (``SeriesId``/``SeriesName``/
        season + episode numbers — live-verified 2026-09-08 on the bundled
        Jellyfin 10.11.11). ``None`` for a malformed row (never fabricate).
        """
        eid = str(it.get("Id") or "")
        if not eid:
            return None
        ud = it.get("UserData") or {}
        item = self._parse_item(it, "Series")  # reuse user_data/runtime parsing
        return {
            "title": str(it.get("Name") or ""),
            "year": int(it["ProductionYear"]) if it.get("ProductionYear") else None,
            "type": "episode",
            "thumb": item.thumb,
            "item_id": eid,
            "jellyfin_url": self._item_web(eid),
            "played": bool(ud.get("Played")),
            "playback_position": self._ticks_to_sec(ud.get("PlaybackPositionTicks")),
            "runtime": self._ticks_to_sec(it.get("RunTimeTicks")),
            "play_count": self._int(ud.get("PlayCount")),
            "last_played": str(ud.get("LastPlayedDate") or "") or None,
            "genres": [str(g) for g in (it.get("Genres") or [])],
            "added": str(it.get("DateCreated") or "") or None,
            "kind": "episode",
            "episode": {
                "number": self._int(it.get("IndexNumber")),
                "season": self._int(it.get("ParentIndexNumber")),
                "series_id": str(it.get("SeriesId") or ""),
                "series_name": str(it.get("SeriesName") or ""),
            },
        }

    def episodes(self, series_id: str, limit: int = 1000) -> list[dict]:
        """Every episode of a series, with per-episode playback facts.

        Episodes carry their own ``UserData`` (Played / PlaybackPositionTicks),
        so resume + watched work per-episode. Ordered by (season, episode).
        """
        if not self._configured() or not series_id:
            return []
        user_id = self._user_id()
        if not user_id:
            return []
        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self._api_token()}&ParentId={series_id}"
               f"&IncludeItemTypes=Episode&Recursive=true"
               f"&SortBy=IndexNumber,ParentIndexNumber&Limit={limit}"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,IndexNumber,ParentIndexNumber")
        try:
            raw = self._fetch_raw(url)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin episodes(%s) failed: %s", series_id, e)
            return []
        out = []
        for it in raw:
            eid = str(it.get("Id", ""))
            if not eid:
                continue
            item = self._parse_item(it, "Series")  # reuses user_data/runtime/thumb parsing
            out.append({
                "id": eid,
                "name": it.get("Name", ""),
                "season": self._int(it.get("ParentIndexNumber")),
                "episode": self._int(it.get("IndexNumber")),
                "thumb": item.thumb,
                "played": bool(item.played),
                "playback_position": self._ticks_to_sec(item.position_ticks),
                "runtime": self._ticks_to_sec(item.runtime_ticks),
            })
        out.sort(key=lambda e: (e["season"], e["episode"]))
        return out

    def search_items(self, q: str, limit: int = 12) -> dict:
        """Owned media + intent hints for the global search (GLOBAL_SEARCH_PLAN).

        Live-verified on Jellyfin 10.11 (2026-09-10): ``/Users/{uid}/Items`` with
        ``searchTerm`` matches Movie/Series/Episode by NAME (episodes match by
        episode name and carry their own per-episode ``UserData``), while People
        and Genres only resolve through ``/Search/Hints`` typed hints. So this
        runs ONE items query for playable rows and ONE hints query for
        Person/Genre/BoxSet rows. Provider ids ride every row for TMDB dedupe.
        """
        from urllib.parse import quote

        if not self._configured():
            return {}
        user_id = self._user_id()
        if not user_id:
            return {}
        fields = ("PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,Genres,"
                  "DateCreated,SeriesId,SeriesName,IndexNumber,ParentIndexNumber,RunTimeTicks")
        items_url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
                     f"?api_key={self._api_token()}&searchTerm={quote(q)}&Recursive=true"
                     f"&IncludeItemTypes=Movie,Series,Episode&Fields={fields}&Limit={limit}")
        items: list[dict] = []
        try:
            for it in self._fetch_raw(items_url):
                row = self._search_item_row(it)
                if row:
                    items.append(row)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin search_items(%r) failed: %s", q, e)

        hints_url = (f"{self.config.JELLYFIN_URL}/Search/Hints"
                     f"?api_key={self._api_token()}&UserId={user_id}"
                     f"&searchTerm={quote(q)}&Limit={limit}")
        people: list[dict] = []
        genres: list[dict] = []
        collections: list[dict] = []
        try:
            import json
            with urllib.request.urlopen(hints_url, timeout=10) as r:
                hints = (json.load(r) or {}).get("SearchHints") or []
            for h in hints[:limit]:
                t = str(h.get("Type") or "")
                if t == "Person":
                    people.append({"id": str(h.get("Id", "")), "name": str(h.get("Name", "")),
                                   "role": str(h.get("PersonType") or "")})
                elif t == "Genre":
                    genres.append({"id": str(h.get("Id", "")), "name": str(h.get("Name", ""))})
                elif t == "BoxSet":
                    collections.append({"id": str(h.get("Id", "")), "name": str(h.get("Name", "")),
                                        "year": h.get("Year")})
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin search hints(%r) failed: %s", q, e)
        return {"items": items, "people": people, "genres": genres, "collections": collections}

    def items_by_person(self, person_id: str, limit: int = 6) -> list[dict]:
        """Owned Movie/Series rows featuring a Person (actor/director drill-down)."""
        if not self._configured() or not person_id:
            return []
        user_id = self._user_id()
        if not user_id:
            return []
        fields = ("PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,Genres,"
                  "DateCreated,SeriesId,SeriesName,IndexNumber,ParentIndexNumber,RunTimeTicks")
        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self._api_token()}&Recursive=true"
               f"&IncludeItemTypes=Movie,Series&PersonIds={person_id}"
               f"&Fields={fields}&Limit={limit}")
        out: list[dict] = []
        try:
            for it in self._fetch_raw(url):
                row = self._search_item_row(it)
                if row:
                    out.append(row)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin items_by_person(%s) failed: %s", person_id, e)
        return out

    def _search_item_row(self, it: dict) -> Optional[dict]:
        """One normalized global-search row from a raw Jellyfin item dict."""
        item_id = str(it.get("Id", ""))
        typ = str(it.get("Type") or "")
        if not item_id or typ not in ("Movie", "Series", "Episode"):
            return None
        parsed = self._parse_item(it, "Series" if typ == "Series" else "Movie")
        ud = it.get("UserData") or {}
        kind = "show" if typ == "Series" else ("episode" if typ == "Episode" else "movie")
        row = {
            "id": item_id,
            "kind": kind,
            "title": str(it.get("Name") or ""),
            "year": it.get("ProductionYear") or None,
            "genres": [str(g) for g in (it.get("Genres") or [])],
            "rating": self._float(it.get("CommunityRating")),
            "provider_ids": dict(parsed.provider_ids or {}),
            "played": bool(ud.get("Played")),
            "playback_position": self._ticks_to_sec(ud.get("PlaybackPositionTicks")),
            "runtime": self._ticks_to_sec(it.get("RunTimeTicks")),
            "play_count": int(ud.get("PlayCount") or 0),
        }
        if typ == "Episode":
            row["series_id"] = str(it.get("SeriesId") or "")
            row["series_name"] = str(it.get("SeriesName") or "")
            row["season"] = self._int(it.get("ParentIndexNumber"))
            row["episode"] = self._int(it.get("IndexNumber"))
        return row

    def refresh_library(self) -> bool:
        """Trigger a full Jellyfin library scan (picks up newly-added media).

        Returns True when Jellyfin accepted the refresh (204). ``POST`` with an
        empty body, server-side.

        **Phase C: deliberately the ADMINISTRATOR's credential, not the profile's.** A library
        scan is server-wide maintenance, not a media read — it returns no item, no watch state and
        no library content, so it cannot leak anything between profiles. Jellyfin requires
        elevation for it (``/Library/Refresh`` answers a profile's token 403 — measured), so
        sending the profile's token would turn a working feature into a silent failure. No
        *content* call may follow this pattern: those all go through :meth:`_api_token`.
        """
        if not self._configured():
            return False
        from api.session import owner_media_token
        url = (f"{self.config.JELLYFIN_URL}/Library/Refresh"
               f"?api_key={owner_media_token(self.config)}")
        try:
            req = urllib.request.Request(url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = 200 <= int(getattr(r, "status", 0)) < 300
            if ok:
                self.invalidate()  # drop the item cache so the scan is seen immediately
            return ok
        except Exception as e:
            logger.warning("Jellyfin library refresh failed: %s", e)
            return False

    @staticmethod
    def _int(v) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def _item_public(self, item: JellyfinItem) -> dict:
        """Player-ready dict shared by recently_added/all_items/continue_watching."""
        return {
            "title": item.name,
            "year": item.year or None,
            "type": "tv" if item.is_series else "movie",
            "thumb": item.thumb,
            "item_id": item.id,
            "jellyfin_url": self._item_web(item.id),
            "played": bool(item.played),
            "playback_position": self._ticks_to_sec(item.position_ticks),
            "runtime": self._ticks_to_sec(item.runtime_ticks),
            "play_count": int(item.play_count or 0),
            "last_played": item.last_played or None,
            # Discovery facts (roadmap item 4) — genre names + DateCreated ISO.
            "genres": list(item.genres or []),
            "added": item.date_added or None,
        }

    def _fetch_raw(self, url: str) -> list[dict]:
        import json
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        return (d or {}).get("Items", []) or []

    def _fetch_list_or_items(self, url: str) -> list[dict]:
        """Fetch a Jellyfin payload that may be a bare list OR ``{"Items": [...]}``.

        ``/Library/VirtualFolders`` returns a top-level list; item listings wrap
        in ``Items``. Normalise both so callers always iterate rows.
        """
        import json
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        if isinstance(d, list):
            return d
        return (d or {}).get("Items", []) or []

    @staticmethod
    def _parse_item(it: dict, item_type: str) -> JellyfinItem:
        pids = {}
        p = it.get("ProviderIds") or {}
        if p.get("Imdb"):
            pids["imdb"] = str(p["Imdb"])
        if p.get("Tmdb"):
            try:
                pids["tmdb"] = int(p["Tmdb"])
            except (TypeError, ValueError, KeyError):
                pass
        if p.get("Tvdb"):
            try:
                pids["tvdb"] = int(p["Tvdb"])
            except (TypeError, ValueError, KeyError):
                pass
        return JellyfinItem(
            name=it.get("Name", ""),
            year=it.get("ProductionYear", 0),
            id=str(it.get("Id", "")),
            thumb=it.get("Thumb", "") or "",
            is_series=(item_type == "Series"),
            provider_ids=pids,
            user_data=it.get("UserData") or {},
            played=bool((it.get("UserData") or {}).get("Played")),
            position_ticks=int((it.get("UserData") or {}).get("PlaybackPositionTicks") or 0),
            runtime_ticks=int(it.get("RunTimeTicks") or 0),
            play_count=int((it.get("UserData") or {}).get("PlayCount") or 0),
            last_played=str((it.get("UserData") or {}).get("LastPlayedDate") or ""),
            genres=[str(g) for g in (it.get("Genres") or [])],
            date_added=str(it.get("DateCreated") or ""),
        )

    def recently_watched(self, limit: int = 12) -> list[dict]:
        """Recently *finished* titles, most-recently-played first.

        Filters the already-fetched library scan for played items and sorts by
        ``UserData.LastPlayedDate`` (items with no recorded date sort last).
        """
        played = [i for i in (self._get_items("Movie") + self._get_items("Series")) if i.played]
        played.sort(key=lambda i: i.last_played or "", reverse=True)
        return [self._item_public(i) for i in played[:limit]]

    def mark_state(self, item_id: str, watched: bool) -> dict:
        """Mark an item watched (``watched=True``) or unwatched via Jellyfin's
        ``/Users/{uid}/PlayedItems`` endpoint.

        Verified live on Jellyfin 10.11.11: watched = ``POST
        PlayedItems/{id}``; unwatched = ``DELETE PlayedItems/{id}`` (the
        ``POST UnplayedItems/{id}`` variant 404s on 10.11 — do not use it).

        Returns the fresh ``{"played": bool, "play_count": int}`` state. Drops the
        scan cache so the next library read reflects the change immediately.
        """
        if not self._configured() or not item_id:
            return {"played": False, "play_count": 0}
        uid = self._user_id()
        if not uid:
            return {"played": False, "play_count": 0}
        method = "POST" if watched else "DELETE"
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/PlayedItems/{item_id}"
               f"?api_key={self._api_token()}")
        try:
            req = urllib.request.Request(url, method=method, data=b"",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                pass
            self.invalidate()  # next library read reflects the change
            return self._user_state(item_id)
        except Exception as e:
            logger.warning("Jellyfin mark_state(%s, %s) failed: %s", item_id, watched, e)
            return {"played": False, "play_count": 0}

    def set_playback_position(self, item_id: str, position_ticks: int) -> bool:
        """Persist a resume position on the ITEM's own user data.

        ⚠ Deliberately NOT Jellyfin's ``/Sessions/Playing*`` endpoints. Those only
        write when the report can be matched to a live *device playback session*,
        which a proxy player never has: Jellyfin answers them **204 and stores
        nothing**, so the item's position stays 0 and it never appears in Continue
        Watching. Verified live 2026-09-11 against 10.11.11 — every shape was
        accepted-and-dropped (real PlaySessionId, invented one, device header,
        X-Emby-Token, Authorization). The user-scoped
        ``/Users/{uid}/Items/{id}/UserData`` write is the one that lands, and it is
        the same endpoint family the working ``mark_state`` uses.

        Sends ONLY ``PlaybackPositionTicks`` + ``LastPlayedDate`` on purpose:
        passing ``Played`` would clobber the watched flag — an explicit
        ``Played: false`` un-marks an already-watched title (verified live), while
        omitting it leaves the flag alone, which is what a position report should
        do.

        ``LastPlayedDate`` is what puts the title at the TOP of Continue Watching.
        Jellyfin's ``/Items/Resume`` (which the app preserves the order of) sorts by
        that field, newest first, **nulls last** — and this endpoint does not set it
        implicitly. Without it a freshly watched title sinks to the END of the rail
        (or off it entirely once the provider's limit applies) even though its
        position was stored: exactly the "resume shows on the item page but Home
        never lists the new entry" symptom. Verified live 2026-09-11: setting it
        moves the item to the head of Resume, and it does NOT disturb ``Played``.

        Returns ``True`` when Jellyfin accepted the write (a 2xx, which for this
        endpoint DOES mean stored — confirmed by reading the position back).
        """
        if not self._configured() or not item_id:
            return False
        uid = self._user_id()
        if not uid:
            return False
        import json
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}/UserData"
               f"?api_key={self._api_token()}")
        body = json.dumps({
            "PlaybackPositionTicks": int(position_ticks),
            "LastPlayedDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ok = int(getattr(r, "status", 200)) < 300
        except Exception as e:
            logger.warning("Jellyfin set_playback_position(%s) failed: %s", item_id, e)
            return False
        self.invalidate()  # the next library/Continue-Watching read sees the position
        return ok

    def _user_state(self, item_id: str) -> dict:
        """Fresh ``{played, play_count}`` for one item, for the state mutation."""
        uid = self._user_id()
        if not uid:
            return {"played": False, "play_count": 0}
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?api_key={self._api_token()}&Fields=UserData")
        try:
            import json
            with urllib.request.urlopen(url, timeout=10) as r:
                it = json.load(r)
            ud = it.get("UserData") or {}
            return {
                "played": bool(ud.get("Played")),
                "play_count": int(ud.get("PlayCount") or 0),
            }
        except Exception as e:
            logger.warning("Jellyfin _user_state(%s) failed: %s", item_id, e)
            return {"played": False, "play_count": 0}

    def get_poster(self, item_id: str, max_width: int = 500, kind: str = "Primary") -> Optional[dict]:
        """Proxy a Jellyfin item's artwork (keeps the token server-side).

        ``kind`` mirrors Jellyfin's image type — ``Primary`` (poster),
        ``Backdrop`` (16:9 keyart), ``Thumb`` (wide banner), etc.

        Returns ``{"content": bytes, "content_type": str, "etag": str|None,
        "last_modified": str|None}`` or None. The validators are FORWARDED to the
        client (see api/routes/jellyfin_poster.py) so a repeat visit can be a
        bodiless 304 instead of re-sending the whole image.
        """
        if not self._configured() or not item_id:
            return None
        url = (f"{self.config.JELLYFIN_URL}/Items/{item_id}/Images/{kind}"
               f"?api_key={self._api_token()}&maxWidth={max_width}&quality=90&tag=")
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                data = r.read()
                content_type = r.headers.get("Content-Type", "image/jpeg")
                etag = r.headers.get("ETag")
                last_modified = r.headers.get("Last-Modified")
            if not data:
                return None
            return {"content": data, "content_type": content_type,
                    "etag": etag, "last_modified": last_modified}
        except Exception as e:
            logger.warning("Jellyfin get_poster(%s/%s) failed: %s", item_id, kind, e)
            return None

    def playback_info(self, item_id: str) -> Optional[dict]:
        """Enumerate an item's audio + *text* subtitle tracks for the player.

        Probes Jellyfin ``POST /Items/{id}/PlaybackInfo`` and normalises the
        first media source's ``MediaStreams`` into player-ready lists. Only
        **text** subtitle streams are returned (``IsTextSubtitleStream``) — an
        image/PGS track can't render in ``<track>`` and is deliberately skipped
        so the picker never offers a subtitle the browser can't draw.

        Returns ``{"media_source_id": str, "container": str, "video":
        {"codec", "profile", "width", "height", "bit_depth", "bit_rate"} | None,
        "audio": [{"index", "name", "language", "codec"}], "subtitles":
        [{"index", "name", "language"}]}`` or None. ``codec`` drives the
        player's audio-transcode decision (EAC3/AC3/DTS/TrueHD aren't
        browser-decodable; AAC/MP3/Opus are); ``container`` + ``video`` drive
        the direct/remux/transcode routing decision.
        """
        if not self._configured() or not item_id:
            return None
        uid = self._user_id()
        if not uid:
            return None
        import json
        url = (f"{self.config.JELLYFIN_URL}/Items/{item_id}/PlaybackInfo"
               f"?api_key={self._api_token()}")
        body = json.dumps({
            "UserId": uid, "StartTimeTicks": 0,
            "AutoOpenLiveStream": False, "MediaSourceId": "",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.load(r)
        except Exception as e:
            logger.warning("Jellyfin playback_info(%s) failed: %s", item_id, e)
            return None

        sources = d.get("MediaSources") or []
        ms0 = sources[0] if sources else {}
        ms_id = str(ms0.get("Id") or "")
        container = str(ms0.get("Container") or "").lower()
        video: Optional[dict] = None
        audio: list[dict] = []
        subtitles: list[dict] = []
        for st in (ms0.get("MediaStreams") or []):
            kind = str(st.get("Type") or "")
            index = st.get("Index")
            if index is None:
                continue
            name = str(st.get("DisplayTitle") or st.get("Language")
                       or f"Track {index}")
            lang = str(st.get("Language") or "")
            if kind == "Video" and video is None:
                video = {
                    "codec": str(st.get("Codec") or "").lower(),
                    "profile": str(st.get("Profile") or ""),
                    "width": int(st.get("Width") or 0),
                    "height": int(st.get("Height") or 0),
                    "bit_depth": int(st.get("BitDepth") or 0),
                    "bit_rate": int(st.get("BitRate") or 0),
                }
            elif kind == "Audio":
                audio.append({
                    "index": int(index), "name": name, "language": lang,
                    "codec": str(st.get("Codec") or "").lower(),
                })
            elif kind == "Subtitle" and bool(st.get("IsTextSubtitleStream")):
                subtitles.append({"index": int(index), "name": name, "language": lang})
        return {
            "media_source_id": ms_id, "container": container, "video": video,
            "audio": audio, "subtitles": subtitles,
        }

    # --- Subtitles (SUBTITLES_OPENSUBTITLES_PLAN §3.3) ------------------------

    def item_path(self, item_id: str) -> Optional[str]:
        """The media file's path, as Jellyfin reports it.

        Live-verified shape: ``GET /Users/{uid}/Items/{id}?Fields=Path`` returns a
        single item with ``Path``. The bundled API container mounts the media roots
        read-WRITE at these same container paths, which is what makes the sidecar
        ``.srt`` design work without installing a plugin.
        """
        if not self._configured() or not item_id:
            return None
        uid = self._user_id()
        if not uid:
            return None
        import json
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?Fields=Path&api_key={self._api_token()}")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.load(r)
        except Exception as e:
            logger.warning("Jellyfin item_path(%s) failed: %s", item_id, e)
            return None
        path = str((data or {}).get("Path") or "")
        return path or None

    def refresh_item(self, item_id: str) -> bool:
        """Re-index ONE item so a newly written sidecar subtitle is indexed.

        ``POST /Items/{id}/Refresh`` with the lightest modes: a metadata refresh to
        pick up the sibling ``.srt`` and no image work, ``replaceAllMetadata=false``
        so nothing already known about the item is thrown away. **Never** a
        library-wide scan — that cancels an in-flight scan (OPERATIONS.md).
        """
        if not self._configured() or not item_id:
            return False
        url = (f"{self.config.JELLYFIN_URL}/Items/{item_id}/Refresh"
               f"?metadataRefreshMode=Default&imageRefreshMode=None"
               f"&replaceAllMetadata=false&replaceAllImages=false"
               f"&api_key={self._api_token()}")
        try:
            req = urllib.request.Request(url, data=b"", method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = int(getattr(r, "status", 200)) < 300
            self.invalidate()   # the next playback-info read must not serve a stale list
            return ok
        except Exception as e:
            logger.warning("Jellyfin refresh_item(%s) failed: %s", item_id, e)
            return False

    def upload_subtitle(self, item_id: str, file_name: str, content: bytes,
                        language: str = "", format: str = "") -> bool:
        """Attach subtitle bytes to an item (``POST /Videos/{id}/Subtitles``).

        The FALLBACK path, used when no sidecar file can be written (the media file
        lives outside the api's mounts). Jellyfin indexes the upload with the item, so
        the existing VTT proxy serves it unchanged.

        ⚠ MEASURED, after a live 415: this endpoint is **JSON**, not multipart. The
        server's own ``/api-docs/openapi.json`` declares an ``UploadSubtitleDto``
        body (``Language``, ``Format``, ``IsForced``, ``IsHearingImpaired``, ``Data``)
        and does not accept ``multipart/form-data`` at all — a hand-built multipart
        post is answered with 415 Unsupported Media Type. ``Data`` is the file's bytes
        as **base64**.
        """
        if not self._configured() or not item_id or not content:
            return False
        import base64
        import json
        ext = format or ((file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else "srt")
        body = json.dumps({
            "Language": language or "eng",
            "Format": ext,
            "IsForced": False,
            "IsHearingImpaired": False,
            "Data": base64.b64encode(content).decode("ascii"),
        }).encode("utf-8")
        url = (f"{self.config.JELLYFIN_URL}/Videos/{item_id}/Subtitles"
               f"?api_key={self._api_token()}")
        try:
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                ok = int(getattr(r, "status", 200)) < 300
            self.invalidate()
            return ok
        except Exception as e:
            logger.warning("Jellyfin upload_subtitle(%s) failed: %s", item_id, e)
            return False

    def subtitle_search_context(self, item_id: str) -> Optional[dict]:
        """The identity an OpenSubtitles search needs (see the ABC for the contract).

        One narrow fetch — provider ids, plus the series context an episode needs. The
        library's episodes carry NO provider ids of their own (measured), so the series
        name + season/episode numbers are what actually make an episode searchable.
        """
        if not self._configured() or not item_id:
            return None
        uid = self._user_id()
        if not uid:
            return None
        import json
        fields = ("ProviderIds,SeriesName,SeriesId,IndexNumber,ParentIndexNumber,"
                  "ProductionYear,Name,Type")
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?Fields={fields}&api_key={self._api_token()}")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                it = json.load(r)
        except Exception as e:
            logger.warning("Jellyfin subtitle_search_context(%s) failed: %s", item_id, e)
            return None
        ids = it.get("ProviderIds") or {}
        tmdb = ids.get("Tmdb")
        return {
            "item_id": str(it.get("Id") or item_id),
            "type": str(it.get("Type") or ""),
            "name": str(it.get("Name") or ""),
            "year": int(it["ProductionYear"]) if it.get("ProductionYear") else None,
            "tmdb_id": int(tmdb) if str(tmdb or "").isdigit() else None,
            "imdb_id": str(ids.get("Imdb") or ""),
            "series_id": str(it.get("SeriesId") or ""),
            "series_name": str(it.get("SeriesName") or ""),
            "season": it.get("ParentIndexNumber"),
            "episode": it.get("IndexNumber"),
        }

    def item_detail(self, item_id: str) -> Optional[dict]:
        """Rich single-item metadata for the Plex-style preplay/detail view.

        Fetches ``/Users/{uid}/Items/{item_id}`` with the full detail field
        list (``DETAIL_FIELDS``) and normalises it into the shape the detail
        route returns — one additive call unlocks the ~90% of a Plex preplay
        screen Jellyfin already stores (docs/PLEX_UI_PLAN.md §1): synopsis,
        genres, community/content ratings, studios, cast/credits (with person
        ids for headshots), backdrop presence, poster aspect and play state.

        Episode items additionally carry their series context
        (``SeriesId``/``SeriesName``/``SeasonId`` + season/episode numbers).
        Returns ``None`` for unknown/non-playable types or on failure.
        """
        if not self._configured() or not item_id:
            return None
        uid = self._user_id()
        if not uid:
            return None
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?api_key={self._api_token()}"
               f"&Fields={self.DETAIL_FIELDS}")
        try:
            import json
            with urllib.request.urlopen(url, timeout=12) as r:
                it = json.load(r)
        except Exception as e:
            logger.warning("Jellyfin item_detail(%s) failed: %s", item_id, e)
            return None
        return self._detail_from_item(it)

    def item_similar(self, item_id: str, limit: int = 10) -> Optional[list[dict]]:
        """\"Because you watched\" — TMDB similar titles for one library item.

        Resolves the item's ``ProviderIds.Tmdb`` with a light single-item fetch
        (the detail fetch's full field list is overkill here), then delegates to
        :class:`TMDBService` for the similarity graph (movie/tv endpoints —
        live-verified 2026-09-08). Returns display rows ``{"id", "title",
        "year", "kind" ("movie"|"show"), "score", "poster", "backdrop"}`` capped
        at *limit*, ``[]`` when TMDB simply has no similar titles, and ``None``
        when the item is missing, isn't a Movie/Series, has no TMDB id, or the
        lookup failed — callers map ``None`` to a 404 (never fabricate).
        """
        if not self._configured() or not item_id:
            return None
        uid = self._user_id()
        if not uid:
            return None
        import json
        url = (f"{self.config.JELLYFIN_URL}/Users/{uid}/Items/{item_id}"
               f"?api_key={self._api_token()}&Fields=ProviderIds")
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                it = json.load(r)
        except Exception as e:  # noqa: BLE001
            logger.warning("Jellyfin item_similar(%s) item fetch failed: %s", item_id, e)
            return None
        if not isinstance(it, dict) or not it.get("Id"):
            return None
        type_name = str(it.get("Type") or "")
        if type_name not in ("Movie", "Series"):
            return None
        media_type = "tv" if type_name == "Series" else "movie"
        try:
            tmdb_id = int((it.get("ProviderIds") or {}).get("Tmdb"))
        except (TypeError, ValueError):
            tmdb_id = 0
        if not tmdb_id:
            return None
        try:
            rows = self._tmdb().get_similar(tmdb_id, media_type)
        except Exception as e:  # noqa: BLE001 - a TMDB failure is a soft miss
            logger.warning("Jellyfin item_similar(%s) tmdb failed: %s", item_id, e)
            return None
        out = []
        for r in rows:
            out.append({
                "id": int(r.get("tmdb_id") or 0),
                "title": str(r.get("title") or ""),
                "year": int(r.get("year") or 0) or None,
                "kind": "show" if r.get("media_type") == "tv" else "movie",
                "score": float(r.get("score") or 0),
                "poster": str(r.get("poster") or ""),
                "backdrop": str(r.get("backdrop") or ""),
            })
            if len(out) >= limit:
                break
        return out

    def _tmdb(self):
        """The TMDB client for similarity lookups (injected in tests)."""
        if self._tmdb_service is None:
            from services.tmdb import TMDBService
            self._tmdb_service = TMDBService(config=self.config, http=self.http)
        return self._tmdb_service

    @classmethod
    def _detail_from_item(cls, it: dict) -> Optional[dict]:
        """Normalise one raw Jellyfin item (single-item fetch) into the detail
        shape. ``None`` for unknown/non-playable item types."""
        if not it or not it.get("Id"):
            return None
        type_map = {"Movie": "movie", "Series": "tv", "Episode": "episode"}
        type_name = type_map.get(str(it.get("Type") or ""))
        if type_name is None:
            return None
        ud = it.get("UserData") or {}
        ticks = cls._int(it.get("RunTimeTicks"))
        resume_ticks = cls._int(ud.get("PlaybackPositionTicks"))
        detail = {
            "type": type_name,
            "item_id": str(it.get("Id")),
            "name": str(it.get("Name") or ""),
            "year": int(it["ProductionYear"]) if it.get("ProductionYear") else None,
            "runtime": cls._ticks_to_sec(ticks),
            "runtime_ticks": ticks,
            "overview": str(it.get("Overview") or ""),
            "genres": [g for g in (it.get("Genres") or []) if g],
            "community_rating": cls._float(it.get("CommunityRating")),
            "official_rating": str(it.get("OfficialRating") or "") or None,
            "studios": [s.get("Name") for s in (it.get("Studios") or [])
                        if isinstance(s, dict) and s.get("Name")],
            "people": cls._detail_people(it.get("People") or []),
            "has_backdrop": bool(it.get("BackdropImageTags"))
                or bool((it.get("ImageTags") or {}).get("Backdrop")),
            "primary_aspect": cls._float(it.get("PrimaryImageAspectRatio")),
            "play": {
                "played": bool(ud.get("Played")),
                "resume_ticks": resume_ticks,
                "resume": cls._ticks_to_sec(resume_ticks),
                "play_count": cls._int(ud.get("PlayCount")),
            },
        }
        if type_name == "episode":
            detail["series"] = {
                "id": str(it.get("SeriesId") or ""),
                "name": str(it.get("SeriesName") or ""),
            }
            detail["season_id"] = str(it.get("SeasonId") or "")
            detail["season"] = cls._int(it.get("ParentIndexNumber"))
            detail["episode"] = cls._int(it.get("IndexNumber"))
        return detail

    @staticmethod
    def _detail_people(people: list) -> dict:
        """Group Jellyfin ``People`` entries into the preplay cast/credits shape.

        Only Actor/Director/Writer surface (Producers and other crew stay out
        of the v1 preplay view). Each entry keeps its person ``Id`` (feeds the
        headshot proxy), ``Name``, character/credit ``Role``, and whether
        Jellyfin reports a ``PrimaryImageTag`` so the UI can skip headshot
        requests for people who have none (verified live: those 404).
        """
        out: dict = {"actors": [], "directors": [], "writers": []}
        for p in people:
            t = str(p.get("Type") or "")
            if t not in ("Actor", "Director", "Writer"):
                continue
            out[{"Actor": "actors", "Director": "directors",
                 "Writer": "writers"}[t]].append({
                "id": str(p.get("Id") or ""),
                "name": str(p.get("Name") or ""),
                "role": str(p.get("Role") or ""),
                "has_image": bool(p.get("PrimaryImageTag")),
            })
        return out

    @staticmethod
    def _float(v) -> Optional[float]:
        """Tolerant float (returns None for missing/NaN), never raises."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f else None  # NaN → None

    def get_library_counts(self) -> dict:
        return {
            "movie": len(self._get_items("Movie")),
            "show": len(self._get_items("Series")),
        }

    def invalidate(self) -> None:
        self._item_cache = None
        self._item_cache_expiry = {}
        self._folders_cache = None
        self._folders_expiry = 0
        self._server_id_value = ""
        self._user_id_value = ""

    def build_watch_link(self, match: LibraryMatch) -> dict:
        item_id = str(match.metadata.get("item_id", "") or "")
        base = self._browser_base()
        if item_id:
            # Jellyfin web 10.10+ uses `#/` routes (NO `#!/` hashbang — that's
            # Emby's legacy form and 404s on Jellyfin — that is Jellyfin's own
            # protocol, kept deliberately).
            return {"jellyfin_url": self._item_web(item_id)}
        q = urllib.parse.quote(str(match.title or ""))
        return {"jellyfin_url": f"{base}#/search?query={q}"}

    def _item_web(self, item_id: str) -> str:
        base = self._browser_base()
        url = f"{base}#/details?id={item_id}"
        sid = self._server_id()
        if sid:
            url += f"&serverId={sid}"
        return url

    # ------------------------------------------------------------------ Jellyfin API
    def _browser_base(self) -> str:
        if self.config.JELLYFIN_BROWSER_URL:
            return self.config.JELLYFIN_BROWSER_URL.rstrip("/") + "/web/index.html"
        if self.config.JELLYFIN_URL and "tail8d5e8.ts.net" in (self.config.JELLYFIN_URL or ""):
            return self.config.JELLYFIN_URL.rstrip("/") + "/web/index.html"
        # Default: bundled Jellyfin on the dashboard host (or plain localhost).
        return f"{self.config.JELLYFIN_URL.rstrip('/')}/web/index.html"

    # ------------------------------------------------------- household accounts
    # AUTH_MULTIUSER_PLAN Phase 1b. The ONLY calls in the app that manage other
    # people's accounts. Every shape below was measured on the RUNNING server
    # (`tools/probe_jellyfin_users.py`) — do not re-derive them:
    #   GET    /Users                    -> [UserDto] (Policy embedded; admin only)
    #   POST   /Users/New   {Name, Password}
    #   GET    /Users/{id}               -> UserDto (Policy embedded)
    #   POST   /Users/{id}/Policy         UserPolicy — the WHOLE object, so every write
    #                                     here is read-modify-write
    #   POST   /Users/Password?userId=   {CurrentPw, NewPw, ResetPassword}
    #   DELETE /Users/{id}
    #
    # ⚠ These go through `_api_token()` too, so while the administrator browses as THEMSELVES they
    # run on their own session token. The route's live administrator check is still the gate that
    # matters (Phase C did not move it): these routes are refused outright whenever somebody
    # else's profile is selected (`require_admin_session`), so Jellyfin's own 403 is the backstop
    # for a demoted account, not the first line of defence.
    def _api_token(self) -> str:
        """The credential every Jellyfin call here is made with.

        Phase C (PLEX_PROFILE_AUTH_PLAN §3): the selected PROFILE's token while a session is in
        effect, else the account that signed in, else — with no request context at all, as in the
        provisioner, the scheduler's jobs and the unit tests — the app's own key. The rule lives in
        ``api.session.acting_media_token`` so this and the routes that build raw upstream URLs
        (stream / subtitle / HLS) can never disagree.

        ⚠ The lookup is a LAZY import on purpose: ``api.session`` imports the library factory at
        module level, so a top-level import here would be circular.
        """
        from api.session import acting_media_token
        return acting_media_token(self.config)

    def _api(self, method: str, path: str, body: Optional[dict] = None) -> tuple[bool, object]:
        """Call Jellyfin and return ``(ok, payload)`` — never raising.

        A dead or refusing server must surface as an honest failure in the route rather
        than as a 500 (the lesson the subtitle client paid for).
        """
        sep = "&" if "?" in path else "?"
        url = f"{self.config.JELLYFIN_URL}{path}{sep}api_key={self._api_token()}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        try:
            req = urllib.request.Request(url, data=data, method=method.upper(),
                                         headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode("utf-8", "replace")
            self._last_api_error = None
            return True, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            # The STATUS only: an error body can name the account, and a body echoing a
            # requested password would be worse. Neither is logged nor returned.
            logger.warning("Jellyfin %s %s -> HTTP %s", method, path, e.code)
            self._last_api_error = {"method": method.upper(), "path": path, "status": e.code}
            return False, {"status": e.code}
        except Exception as e:
            logger.warning("Jellyfin %s %s failed: %s", method, path, type(e).__name__)
            self._last_api_error = {"method": method.upper(), "path": path,
                                    "error": type(e).__name__}
            return False, {"error": type(e).__name__}

    def last_api_error(self) -> Optional[dict]:
        """Why the most recent ``_api`` call failed, or ``None``.

        Exists so a LISTING can say "the server refused us" instead of showing an empty
        household, which would read as "there are no accounts".
        """
        return self._last_api_error

    @staticmethod
    def _user_row(user: dict) -> dict:
        """One account, normalised for the app. Never carries a password."""
        policy = user.get("Policy") or {}
        return {
            "id": str(user.get("Id") or ""),
            "name": str(user.get("Name") or ""),
            "is_admin": bool(policy.get("IsAdministrator")),
            "disabled": bool(policy.get("IsDisabled")),
            "has_password": bool(user.get("HasPassword")),
            "enable_all_folders": bool(policy.get("EnableAllFolders")),
            "enabled_folders": [str(f) for f in (policy.get("EnabledFolders") or [])],
            "last_login": str(user.get("LastLoginDate") or ""),
        }

    def list_users(self) -> list[dict]:
        """Every account on the server (Jellyfin requires an admin credential)."""
        if not self._configured():
            return []
        ok, payload = self._api("GET", "/Users")
        if not ok or not isinstance(payload, list):
            return []
        return [self._user_row(u) for u in payload if isinstance(u, dict)]

    def get_user_policy(self, user_id: str) -> Optional[dict]:
        """The FULL policy for one account — where a read-modify-write must start."""
        if not self._configured() or not user_id:
            return None
        ok, payload = self._api("GET", f"/Users/{urllib.parse.quote(str(user_id))}")
        if not ok or not isinstance(payload, dict):
            return None
        return dict(payload.get("Policy") or {})

    def create_user(self, name: str, password: str = "") -> Optional[dict]:
        """Create an account. The password is OPTIONAL — a member may have none."""
        if not self._configured() or not str(name or "").strip():
            return None
        body: dict = {"Name": str(name).strip()}
        # Only send a password when there IS one: an empty `Password` is not the same
        # request as omitting it, and "this member has no password" is the point.
        if password:
            body["Password"] = str(password)
        ok, payload = self._api("POST", "/Users/New", body)
        if not ok or not isinstance(payload, dict):
            return None
        return self._user_row(payload)

    def mutate_user_policy(self, user_id: str, mutate) -> Optional[dict]:
        """Read-modify-write one account's policy — the ONLY safe way to change it.

        ``POST /Users/{id}/Policy`` REPLACES the whole 47-field object, so a partial body
        silently resets everything it omits (measured on the live server 2026-09-12). This
        fetches the current policy, lets ``mutate`` change just its own keys, and posts the
        WHOLE thing back.
        """
        current = self.get_user_policy(user_id)
        if current is None:
            return None
        updated = dict(current)
        mutate(updated)
        ok, _ = self._api("POST", f"/Users/{urllib.parse.quote(str(user_id))}/Policy", updated)
        return updated if ok else None

    def set_folder_access(self, user_id: str, library_ids: Optional[list] = None,
                          *, enable_all: bool = False) -> Optional[dict]:
        """Grant EXACTLY these libraries (with ``EnableAllFolders=false``).

        A grant is a library **ItemId** in ``Policy.EnabledFolders`` (the value
        ``/Library/VirtualFolders`` reports); a wrong id grants nothing and reads like
        "the app hid my library".
        """
        ids = [str(i) for i in (library_ids or []) if str(i or "").strip()]

        def mutate(policy: dict) -> None:
            policy["EnableAllFolders"] = bool(enable_all)
            policy["EnabledFolders"] = [] if enable_all else ids

        return self.mutate_user_policy(user_id, mutate)

    def set_user_disabled(self, user_id: str, disabled: bool) -> Optional[dict]:
        """Enable/disable an account; its watch state is untouched either way."""
        return self.mutate_user_policy(
            user_id, lambda policy: policy.update({"IsDisabled": bool(disabled)}))

    def set_user_password(self, user_id: str, new_password: str, *,
                          reset: bool = True) -> bool:
        """Set or RESET another account's password.

        ⚠ The target is a QUERY parameter (``/Users/Password?userId=``), NOT a path
        segment — the path form 404s (measured live). ``ResetPassword: true`` is what lets
        an administrator change somebody else's password without knowing the old one.
        """
        if not self._configured() or not user_id:
            return False
        ok, _ = self._api(
            "POST", f"/Users/Password?userId={urllib.parse.quote(str(user_id))}",
            {"CurrentPw": "", "NewPw": str(new_password), "ResetPassword": bool(reset)})
        return ok

    def rename_user(self, user_id: str, name: str) -> Optional[dict]:
        """Rename an account — a read-modify-write of the account, never a partial body.

        ⚠ Measured from the server's OWN contract (2026-09-12): the target is a **QUERY**
        parameter (``POST /Users?userId=``), not a path segment, and the body is a ``UserDto``
        (14 properties, ``Name`` nullable, **and a ``Policy``**).

        That ``Policy`` field is why this does not simply send ``{"Name": …}``. The sibling trap on
        ``/Users/{id}/Policy`` was already paid for once — a partial body there replaced all 47
        fields — and if ``POST /Users`` shares those semantics, a name-only body would wipe the
        account's permissions (an administrator losing ``IsAdministrator`` is a LOCKOUT).

        So the body carries the id, the name and the policy **as the server just reported them**.
        That is correct under EITHER semantics: a merge sees only the renamed field change, and a
        wholesale replace receives the identical policy back. ``HasPassword`` is deliberately NOT
        sent — whether a client could clear a password through it is not something this route needs
        to find out the hard way.
        """
        if not self._configured() or not user_id or not str(name or "").strip():
            return None
        quoted = urllib.parse.quote(str(user_id))
        ok, current = self._api("GET", f"/Users/{quoted}")
        if not ok or not isinstance(current, dict):
            return None
        body = {
            "Id": str(current.get("Id") or user_id),
            "Name": str(name).strip(),
            "Policy": current.get("Policy"),
        }
        ok, updated = self._api("POST", f"/Users?userId={quoted}", body)
        if not ok or not isinstance(updated, dict):
            return None
        return self._user_row(updated)

    def delete_user(self, user_id: str) -> bool:
        """Delete an account. IRRREVERSIBLE — the route owns the rails around this."""
        if not self._configured() or not user_id:
            return False
        ok, _ = self._api("DELETE", f"/Users/{urllib.parse.quote(str(user_id))}")
        return ok

    def _user_id(self) -> str:
        """The Jellyfin user every media call is scoped to.

        **Phase C:** the selected PROFILE while a session is in effect. The id comes from the SAME
        session as the token (``api.session.acting_user_id``), which is what keeps the pair
        consistent — Jellyfin takes the user id in the PATH of the user-scoped endpoints, so naming
        the administrator while presenting a profile's token is a contradiction it answers with a
        404 (measured — plan §4d).

        With **no** request context the historical lookup is unchanged (the server's first account,
        i.e. the administrator): the provisioner, the scheduler's jobs and every tool depend on it.
        """
        from api.session import acting_user_id
        session_user = acting_user_id()
        if session_user:
            return session_user
        if self._user_id_value:
            return self._user_id_value
        try:
            import json
            with urllib.request.urlopen(
                f"{self.config.JELLYFIN_URL}/Users?api_key={self._api_token()}",
                timeout=8,
            ) as r:
                users = json.load(r)
            if users:
                self._user_id_value = str(users[0].get("Id", ""))
        except Exception as e:
            logger.warning("Jellyfin _user_id failed: %s", e)
            self._user_id_value = ""
        return self._user_id_value

    def _get_items(self, item_type: str) -> list[JellyfinItem]:
        import time
        now = time.time()
        # Per-type cache so a busy Movie path can't keep a stale-empty Series
        # cache alive via a shared expiry (the bug that hid newly-added shows).
        if self._item_cache and now < self._item_cache_expiry.get(item_type, 0):
            return self._item_cache.get(item_type, [])

        if not self._configured():
            return []

        user_id = self._user_id()
        if not user_id:
            return []

        url = (f"{self.config.JELLYFIN_URL}/Users/{user_id}/Items"
               f"?api_key={self._api_token()}"
               f"&Recursive=true&IncludeItemTypes={item_type}"
               f"&Fields=PrimaryImageAspectRatio,ProductionYear,ProviderIds,UserData,Genres,DateCreated")
        try:
            raw = self._fetch_raw(url)
            items = [self._parse_item(it, item_type) for it in raw]
            if self._item_cache is None:
                self._item_cache = {}
            self._item_cache[item_type] = items
            self._item_cache_expiry[item_type] = now + self.JELLYFIN_SCAN_TTL
            return items
        except Exception as e:
            logger.warning("Jellyfin _get_items(%s) failed: %s", item_type, e)
            return []

    def _server_id(self) -> str:
        if self._server_id_value:
            return self._server_id_value
        try:
            import json
            with urllib.request.urlopen(f"{self.config.JELLYFIN_URL}/System/Info/Public", timeout=8) as r:
                d = json.load(r)
            self._server_id_value = str(d.get("Id") or d.get("ServerId") or "")
        except Exception:
            self._server_id_value = ""
        return self._server_id_value