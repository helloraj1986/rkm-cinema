"""Subtitle search / select / disable (SUBTITLES_OPENSUBTITLES_PLAN §3.5, Phase 3).

Additive only (ADR-0001): three new paths, and ONE new field on the existing
``playback-info`` response so the player needs no extra round trip to apply the user's
choice on load.

Division of labour, deliberately:

* the **api** owns the OpenSubtitles credential and the store; nothing about either
  reaches the browser (criterion 11);
* a vendor failure degrades THIS route only — local embedded/on-disk subtitles keep
  working and playback is never blocked (criterion 10), so a search error is reported
  as a ``warning`` in a 200 payload rather than failing the request. Only an ACTION the
  user explicitly asked for (select) can fail the request.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.models import (SubtitleAutoRequest, SubtitleDisableRequest,
                        SubtitleSelectRequest, SubtitleSettingsRequest)
from config.settings import get_config
from services.library.factory import build_library_service
from services.opensubtitles import (AuthFailedError, NotConfiguredError, NoResultsError,
                                    OpenSubtitlesError, QuotaExhaustedError,
                                    RateLimitedError, TransportError,
                                    UnsupportedFormatError, build_opensubtitles_client)
from services.subtitle_store import SubtitleStore
from services.subtitles import (AUTO_PICK_REASONS, SubtitleService, auto_pick_basis,
                                auto_pick_blocked, auto_pick_candidate, auto_pick_language,
                                auto_pick_shortfall, merge_subtitle_rows, search_keywords)

router = APIRouter()
logger = logging.getLogger("rkm.api.subtitles")


def _http_for(exc: OpenSubtitlesError) -> HTTPException:
    """Map the client's error taxonomy onto honest status codes.

    Each of these is a state the USER can act on, so none of them may surface as a
    500: not configured (503), credentials rejected (502), throttled vs out of daily
    downloads (429, the latter with the reset time in the message), nothing usable
    found (400), upstream/network (502).
    """
    if isinstance(exc, NotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, AuthFailedError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, QuotaExhaustedError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return HTTPException(status_code=429, detail=str(exc), headers=headers)
    if isinstance(exc, (NoResultsError, UnsupportedFormatError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TransportError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/jellyfin/subtitle-search")
def subtitle_search(
    id: str = Query(default="", description="Jellyfin item id (movie or episode)"),
    language: str = Query(default="", description="ISO code; blank = the configured default"),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Every subtitle choice for an item: its LOCAL tracks, then OpenSubtitles results.

    Local tracks are always returned and never altered (criterion 9). Each row carries
    our own usage count and ``active`` so the panel can mark the user's choice without a
    second call; remote rows are ranked by our usage first, then the provider's
    popularity (criterion 8).
    """
    cfg = get_config()
    if not id:
        raise HTTPException(status_code=404, detail="Missing item id")
    library = build_library_service(cfg)
    service = SubtitleService(library=library, config=cfg)
    store = SubtitleStore(config=cfg)

    tracks = service.local_tracks(id)
    stored = store.preference(id) or {}
    preferred = store.preferred_subtitle(id, tracks)
    counts = store.usage_counts()
    # Per-row "last used" so the panel can show recency, not just a count.
    usage_rows = (store.load().get("usage") or {})
    last_used = {str(row.get("subtitle_id") or f"os:{key}"): str(row.get("last_used") or "")
                 for key, row in usage_rows.items() if isinstance(row, dict)}

    enabled = bool(cfg.has_opensubtitles())
    remote, warning, remaining = [], "", None
    language = (language or "").strip().lower() or (cfg.opensubtitles_languages() or ["en"])[0]
    if enabled:
        keywords = search_keywords(library.subtitle_search_context(id) or {})
        if keywords:
            try:
                client = build_opensubtitles_client(cfg)
                remote = client.search(languages=[language], limit=limit, **keywords)
                remaining = client.last_quota()
                del client
            except OpenSubtitlesError as exc:
                # Degrade, never break: the local tracks are still a complete answer.
                logger.info("subtitle search degraded for %s: %s", id, exc)
                warning = str(exc)
            except Exception:  # a PASSIVE listing must never 500 (Phase 5 hardening)
                # An UNEXPECTED failure — a vendor payload shape change, a parser bug —
                # must still not take the picker down: the item's own tracks are already
                # a complete answer, and the player must keep working. Logged with a
                # traceback so it is visible, reported as a warning so the user knows why
                # the online list is empty instead of silently seeing nothing.
                logger.exception("subtitle search failed unexpectedly for %s", id)
                warning = "Subtitle search failed — see the api log"
        else:
            warning = "Could not determine a title to search for this item"
    else:
        warning = ("OpenSubtitles is not configured — set OPENSUBTITLES_API_KEY in .env "
                   "to search online subtitles")

    # ⚠ THE AUTO-PICK'S OWN FACTS, on the listing the pane already fetches: which row the
    # rule WOULD take (`auto.subtitle_id`, with `basis` = why it is first) and whether
    # anything is blocking it here (`auto.blocked`, one of the codes in AUTO_PICK_REASONS).
    # ⚠ This is the badge's source and the settings row's source in one payload — a client
    # that had to call a second endpoint to draw either could render them disagreeing.
    auto_language = auto_pick_language(cfg.opensubtitles_languages())
    candidate = auto_pick_candidate(remote, language=language, counts=counts)
    blocked = auto_pick_blocked(settings=store.settings(),
                                stored_preference=stored or None,
                                tracks=tracks,
                                audio_language=_first_audio_language(library, id),
                                language=language)
    auto = {
        "subtitle_id": (getattr(candidate, "subtitle_id", "") if candidate else ""),
        "basis": auto_pick_basis(candidate, counts),
        "blocked": blocked,
        "reason": AUTO_PICK_REASONS.get(blocked, ""),
    }

    return JSONResponse({
        "item_id": id,
        "enabled": enabled,
        "language": language,
        "languages": cfg.opensubtitles_languages(),
        "results": merge_subtitle_rows(tracks, remote, counts=counts,
                                       active_index=(preferred or {}).get("index"),
                                       active_subtitle_id=(preferred or {}).get("subtitle_id"),
                                       last_used=last_used),
        "local_count": len(tracks),
        "remote_count": len(remote),
        "preferred_subtitle": preferred,
        "disabled": bool(stored.get("disabled")),
        "remaining_downloads": remaining,
        "warning": warning,
        "settings": store.settings(),
        "auto_language": auto_language,
        "auto": auto,
    })


def _settings_payload(cfg, store) -> dict:
    """The auto-pick settings, as both clients read them — ONE shape, ONE source.

    ⚠ The LANGUAGE is computed here, from `.env`, and never stored: his decision 3 makes the
    configured list the single source of truth, so changing `OPENSUBTITLES_LANGUAGES` moves
    the auto-pick with no state to migrate and nothing that can disagree with it.
    """
    return {
        "settings": store.settings(),
        "language": auto_pick_language(cfg.opensubtitles_languages()),
        "languages": cfg.opensubtitles_languages(),
        "enabled": bool(cfg.has_opensubtitles()),
    }


def _first_audio_language(library, item_id: str) -> str:
    """The item's own audio language — the input to `auto_pick_skip_audio` (his decision 2).

    ⚠ A failure to read it is ``""``, NOT a block: the exclusion is an extra guard, and a
    Jellyfin hiccup must not silently disable a feature the user turned on.
    """
    try:
        info = library.playback_info(item_id) or {}
    except Exception as e:  # noqa: BLE001 - a metadata miss is not an error state
        logger.info("audio language unavailable for %s: %s", item_id, e)
        return ""
    for track in (info.get("audio") or []):
        code = str((track or {}).get("language") or "").strip()
        if code:
            return code
    return ""


@router.get("/jellyfin/subtitle-settings")
def subtitle_settings() -> JSONResponse:
    """The auto-pick settings + the language they act on (read by every client on open)."""
    cfg = get_config()
    return JSONResponse(_settings_payload(cfg, SubtitleStore(config=cfg)))


@router.post("/jellyfin/subtitle-settings")
def subtitle_settings_update(payload: SubtitleSettingsRequest) -> JSONResponse:
    """Change the auto-pick settings — the global switch and the audio-language exclusion.

    ⚠ **A partial update**: a field left out of the body is left alone in the store. Two
    clients own one control each, and a whole-block write would let one reset the other's
    field the moment their defaults disagreed.
    """
    cfg = get_config()
    store = SubtitleStore(config=cfg)
    store.update_settings(auto_pick=payload.auto_pick,
                          auto_pick_skip_audio=payload.auto_pick_skip_audio)
    return JSONResponse(_settings_payload(cfg, store))


def _auto_reply(*, item_id: str, decision: str, cfg, store, language: str, tracks,
                detail: str = "", applied=None, subtitles=None, preferred=None,
                remaining=None, used=0) -> JSONResponse:
    """One shape for every outcome of the auto-pick, applied or not.

    ⚠⚠ **A DECLINE IS A 200, ALWAYS.** The viewer did not ask for this download — the app
    did, on their behalf — so a refusal is information (``decision`` + the sentence for it,
    from the one vocabulary in `subtitles.AUTO_PICK_REASONS`) and never an error the player
    has to survive. Only a malformed REQUEST is a 4xx.
    """
    return JSONResponse({
        "ok": applied is not None,
        "item_id": item_id,
        "decision": decision,
        "reason": AUTO_PICK_REASONS.get(decision, ""),
        "detail": detail,
        "applied": applied,
        "language": language,
        "settings": store.settings(),
        "remaining_downloads": remaining,
        "used_count": used,
        "subtitles": tracks if subtitles is None else subtitles,
        "preferred_subtitle": (preferred if preferred is not None
                               else store.preferred_subtitle(item_id, tracks or [])),
    })


@router.post("/jellyfin/subtitle-auto")
def subtitle_auto(payload: SubtitleAutoRequest) -> JSONResponse:
    """**Choose and apply the top-ranked subtitle for an untouched title — ONCE.**

    His decision, 2026-09-21: *"apply the most downloaded subtitle automatically by default
    .. user can choose to off it later"*. The whole rule is `SUBTITLE_AUTOPICK_PLAN.md` §2,
    and the two halves of it are composed here in the order that costs nothing first:

    1. `auto_pick_blocked` — every gate knowable LOCALLY (the switch, an existing choice —
       including a per-title `Off` — the item's own tracks, the audio-language exclusion).
       ⚠ **A blocked title returns before a single request is made**, so the switch and the
       exclusions cost no quota and no network.
    2. the search (which is all this needs) → `auto_pick_shortfall` — the quota and the
       candidate.
    3. `attach` + `set_preference` + `record_use` — **the SAME writes a manual pick makes**,
       so from here on the subtitle is indistinguishable from one he chose, `Active` in the
       pane, and costs **one download per title, ever**. `record_use` is what ranks it next
       time (criterion 7).
    """
    cfg = get_config()
    item_id = (payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")

    store = SubtitleStore(config=cfg)
    language = auto_pick_language(cfg.opensubtitles_languages())
    library = build_library_service(cfg)
    tracks = SubtitleService(library=library, config=cfg).local_tracks(item_id)

    blocked = auto_pick_blocked(settings=store.settings(),
                                stored_preference=store.preference(item_id),
                                tracks=tracks,
                                audio_language=_first_audio_language(library, item_id),
                                language=language)
    if blocked:
        return _auto_reply(item_id=item_id, decision=blocked, cfg=cfg, store=store,
                           language=language, tracks=tracks)

    if not cfg.has_opensubtitles():
        return _auto_reply(item_id=item_id, decision="not_configured", cfg=cfg, store=store,
                           language=language, tracks=tracks)

    keywords = search_keywords(library.subtitle_search_context(item_id) or {})
    if not keywords:
        return _auto_reply(item_id=item_id, decision="no_search_terms", cfg=cfg, store=store,
                           language=language, tracks=tracks)

    counts = store.usage_counts()
    client = None
    try:
        client = build_opensubtitles_client(cfg)
        remote = client.search(languages=[language], limit=25, **keywords)
        # ⚠ ASK THE ACCOUNT, don't guess. `/infos/user` is UNMETERED and needs a login, and it
        # is the only way to know the allowance BEFORE a download is spent. Without it (an
        # anonymous key) the last download's number is all that exists — hence
        # `quota_unknown` rather than a hopeful attempt, which is his decision 1.
        info = client.user_info()
        remaining = info.remaining if info is not None else client.last_quota()
    except OpenSubtitlesError as exc:
        # A vendor failure on an AUTOMATIC path is a state, not an error: the player keeps
        # playing and the pane still lists the item's own tracks.
        logger.info("subtitle auto-pick search failed for %s: %s", item_id, exc)
        return _auto_reply(item_id=item_id, decision="unavailable", cfg=cfg, store=store,
                           language=language, tracks=tracks, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - an unexpected payload must not 500 the player
        logger.exception("subtitle auto-pick failed unexpectedly for %s", item_id)
        return _auto_reply(item_id=item_id, decision="unavailable", cfg=cfg, store=store,
                           language=language, tracks=tracks, detail=str(exc))

    candidate = auto_pick_candidate(remote, language=language, counts=counts)
    shortfall = auto_pick_shortfall(remaining=remaining, candidate=candidate)
    if shortfall:
        return _auto_reply(item_id=item_id, decision=shortfall, cfg=cfg, store=store,
                           language=language, tracks=tracks, remaining=remaining)

    # ⚠ THE SAME CLIENT the search used is INJECTED into the delivery service — one
    # OpenSubtitles identity per request, not two (a second client would log in again for
    # the download, and a login is a request the user pays for in latency).
    service = SubtitleService(client=client, library=library, config=cfg)
    try:
        result = service.attach(item_id=item_id, file_id=int(candidate.file_id),
                                language=language, display_title=candidate.display_title)
    except QuotaExhaustedError as exc:
        return _auto_reply(item_id=item_id, decision="quota_exhausted", cfg=cfg, store=store,
                           language=language, tracks=tracks, detail=str(exc))
    except OpenSubtitlesError as exc:
        logger.info("subtitle auto-pick attach failed for %s: %s", item_id, exc)
        return _auto_reply(item_id=item_id, decision="unavailable", cfg=cfg, store=store,
                           language=language, tracks=tracks, detail=str(exc))

    used = store.record_use(item_id, subtitle_id=result.subtitle_id,
                            language=result.language, display_title=result.display_title)
    store.set_preference(item_id, subtitle_id=result.subtitle_id, language=result.language,
                         provider="opensubtitles", display_title=result.display_title)
    applied = {
        "subtitle_id": result.subtitle_id,
        "file_id": int(candidate.file_id),
        "language": result.language,
        "display_title": result.display_title,
        "download_count": int(getattr(candidate, "download_count", 0) or 0),
        "basis": auto_pick_basis(candidate, counts),
    }
    return _auto_reply(item_id=item_id, decision="apply", cfg=cfg, store=store,
                       language=language, tracks=tracks, applied=applied,
                       subtitles=result.tracks, remaining=result.remaining, used=used)


@router.post("/jellyfin/subtitle-select")
def subtitle_select(payload: SubtitleSelectRequest):
    """Download, attach and REMEMBER a subtitle, then return the refreshed tracks.

    One call does the whole user action: fetch the bytes, write them beside the media
    (or upload them), refresh the item, persist the choice and increment its usage
    count. A repeat selection of something already attached is a no-op download-wise
    (the delivery layer reuses it), so the usage count reflects deliberate choices.
    """
    cfg = get_config()
    item_id = (payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    if not payload.file_id:
        raise HTTPException(status_code=400, detail="file_id is required")
    language = (payload.language or "").strip().lower() or \
        (cfg.opensubtitles_languages() or ["en"])[0]

    # Construct the client HERE and inject it: the route is the single place that owns
    # the OpenSubtitles credential wiring, which also keeps the delivery layer free of
    # any notion of how a client is built (and lets a test inject a fake one).
    service = SubtitleService(client=build_opensubtitles_client(cfg),
                              library=build_library_service(cfg), config=cfg)
    try:
        result = service.attach(item_id=item_id, file_id=int(payload.file_id),
                                language=language, display_title=payload.display_title or "")
    except OpenSubtitlesError as exc:
        logger.info("subtitle select failed for %s: %s", item_id, exc)
        raise _http_for(exc)

    store = SubtitleStore(config=cfg)
    store.set_preference(item_id, subtitle_id=result.subtitle_id, language=result.language,
                         provider="opensubtitles", display_title=result.display_title)
    used = store.record_use(item_id, subtitle_id=result.subtitle_id,
                            language=result.language, display_title=result.display_title)
    return JSONResponse({
        "ok": True,
        "delivered": result.delivered,
        "reused": result.reused,
        "subtitles": result.tracks,
        "used_count": used,
        "remaining_downloads": result.remaining,
        "preferred_subtitle": store.preferred_subtitle(item_id, result.tracks),
    })


@router.post("/jellyfin/subtitle-disable")
def subtitle_disable(payload: SubtitleDisableRequest):
    """Turn subtitles off for an item, KEEPING the choice (re-enable is one tap)."""
    cfg = get_config()
    item_id = (payload.item_id or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    store = SubtitleStore(config=cfg)
    store.disable(item_id)
    return JSONResponse({"ok": True, "disabled": True, "preferred_subtitle": None})
