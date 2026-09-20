"""Subtitle delivery: OpenSubtitles bytes → a track Jellyfin can serve
(SUBTITLES_OPENSUBTITLES_PLAN §3.3, Phase 2).

This is the orchestration layer, and it is the only place that WRITES to the media
drive. Its rules, in the order they matter:

1. **The server owns subtitle storage.** We hand Jellyfin a sidecar ``.srt`` beside
   the media file and let it index that file. Jellyfin's own provider and Bazarr
   deliver subtitles exactly the same way, so an existing on-disk subtitle and one of
   ours are indistinguishable to the player, the VTT proxy and the cue renderer —
   nothing downstream needs to change.
2. **Refresh the ITEM, never the library.** A library scan is expensive and CANCELS
   an in-flight scan (OPERATIONS.md), which leaves the user's library half-indexed
   for hours. There is a test that asserts a scan is never triggered.
3. **Never touch a subtitle file we did not write.** A same-language sidecar already
   on disk is REUSED, so a repeat request costs no download and the user's own
   subtitle is left alone. Overwriting happens only when the caller explicitly asks
   for a replacement.
4. **A download is never repeated for something already delivered.** The OpenSubtitles
   client is only called when bytes are actually needed.
5. **Fallback, not failure:** when no sidecar can be written (the media file is
   outside the api's mounts, or the write is refused), the bytes go to the server's
   own ``/Videos/{id}/Subtitles`` upload instead.

Phase 3 adds the preference/usage store on top; this module stays the thing that
touches files and the server.
"""
from __future__ import annotations

import logging
import os
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from services.opensubtitles import (DownloadedSubtitle, OpenSubtitlesClient,
                                    UnsupportedFormatError)

logger = logging.getLogger("rkm.subtitles")

#: Extensions we will write. Text-based only — a bitmap subtitle (.sub/.idx) cannot
#: be rendered by the player and is rejected at the client already.
TEXT_EXTS = ("srt", "vtt", "ass", "ssa")

#: Sanity markers for a real subtitle payload. A "download" that returns an HTML
#: error page is a 200 with a body full of markup; writing that beside the media
#: would give the user a track that renders as garbage, so it is refused.
_SRT_MARKER = "-->"
_ASS_MARKERS = ("[Script Info]", "[V4+ Styles]", "Dialogue:")

#: ISO 639-2/B codes whose FIRST TWO LETTERS do not give the 639-1 code the subtitle
#: APIs use (German is ``ger``, not ``ge``). Everything else maps by its prefix.
_ISO639_2_EXCEPTIONS = {
    "ger": "de", "deu": "de", "fre": "fr", "fra": "fr", "dut": "nl", "nld": "nl",
    "cze": "cs", "ces": "cs", "gre": "el", "ell": "el", "rum": "ro", "ron": "ro",
    "slo": "sk", "slk": "sk", "chi": "zh", "zho": "zh", "may": "ms", "msa": "ms",
    "per": "fa", "fas": "fa", "alb": "sq", "sqi": "sq", "arm": "hy", "hye": "hy",
    "geo": "ka", "kat": "ka", "ice": "is", "isl": "is", "mac": "mk", "mkd": "mk",
    "mao": "mi", "mri": "mi", "wel": "cy", "cym": "cy", "bur": "my", "mya": "my",
    "tib": "bo", "bod": "bo", "scc": "sr", "srp": "sr", "swe": "sv",
}


@dataclass
class AttachResult:
    """What happened, in a shape both the API route and the store can use."""

    item_id: str
    language: str
    subtitle_id: str
    display_title: str
    file_name: str = ""
    sidecar_path: str = ""
    #: "sidecar" | "upload" | "" (nothing delivered)
    delivered: str = ""
    #: True when an existing same-language sidecar was reused (no download spent).
    reused: bool = False
    #: Refreshed track list straight from the server (what the player picks from).
    tracks: List[dict] = field(default_factory=list)
    #: Downloads left today as the API reported, when it told us.
    remaining: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.delivered in ("sidecar", "upload")

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "subtitle_id": self.subtitle_id,
            "language": self.language,
            "display_title": self.display_title,
            "file_name": self.file_name,
            "delivered": self.delivered,
            "reused": self.reused,
            "remaining": self.remaining,
            "subtitles": self.tracks,
        }


# ----------------------------------------------------------------------- helpers
def sidecar_path_for(video_path: str, language: str, ext: str = "srt") -> str:
    """``/data/Movies/Film.2009.mp4`` + ``en`` → ``/data/Movies/Film.2009.en.srt``.

    The convention every media server understands (Kodi/Jellyfin/Bazarr). A stem that
    already ends with the language tag (``Film.2009.en.mp4``) does not get it twice.
    """
    p = Path(video_path)
    lang = (language or "en").strip().lower()[:3]
    stem = p.stem
    if stem.lower().endswith(f".{lang}"):
        return str(p.with_name(f"{stem}.{ext}"))
    return str(p.with_name(f"{stem}.{lang}.{ext}"))


def decode_subtitle(data: bytes) -> tuple[str, str]:
    """Decode subtitle bytes to text, returning ``(text, encoding_used)``.

    Tries the encodings real subtitle files actually arrive in: UTF-8 (with or
    without a BOM), UTF-16 (BOM-detected), then the Windows/Latin fallbacks that old
    ``.srt`` rips use. Line endings are normalised to ``\\n`` and the text is
    guaranteed to end with a newline, because Jellyfin's parser is happier (and the
    last cue safer) with a terminated file.
    """
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        candidates = ("utf-16",)
    elif data.startswith(b"\xef\xbb\xbf"):
        candidates = ("utf-8-sig",)
    else:
        candidates = ("utf-8", "cp1252", "latin-1")
    for enc in candidates:
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 accepts any byte sequence
        text = data.decode("utf-8", "replace")
        enc = "utf-8(replace)"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text, enc


def looks_like_subtitle_text(text: str) -> bool:
    """True when the payload is plausibly a subtitle file (not an HTML error page).

    Cheap and deliberately loose: one of the format markers must appear near the top.
    """
    head = (text or "")[:4000]
    if _SRT_MARKER in head:
        return True
    return any(marker in head for marker in _ASS_MARKERS)


def write_atomic(path: str, text: str) -> None:
    """Write text next to *path* and atomically replace it (tmp + ``os.replace``).

    Same pattern as the watchlist store: a reader (Jellyfin's scanner) can never see
    a half-written file, and a crash mid-write leaves the original untouched. If the
    replace itself fails (a read-only mount, a directory in the way), our temp file is
    removed rather than left behind in the user's media folder.
    """
    target = Path(path)
    tmp = target.with_name(target.name + ".rkm-tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, target)
    except OSError:
        _safe_unlink(tmp)
        raise


def _safe_unlink(path: Path) -> None:
    """Best-effort tidy-up of our own temp file (never the target)."""
    try:
        if path.exists():
            path.unlink()
    except OSError:  # pragma: no cover - nothing to do about it
        logger.debug("could not remove temp file %s", path)


# ------------------------------------------------------------------------ service
class SubtitleService:
    """Delivers a chosen subtitle to Jellyfin and reports the refreshed tracks.

    Collaborators are injected (both have real defaults) so tests never touch the
    network or the media drive:

    * ``client``  — :class:`~services.opensubtitles.OpenSubtitlesClient`;
    * ``library`` — :class:`~services.library.service.LibraryService` (or any object
      with ``item_path`` / ``refresh_item`` / ``upload_subtitle`` / ``playback_info``).
    """

    def __init__(self, *, client=None, library=None, config=None):
        self._client = client
        self._library = library
        self._config = config

    # ------------------------------------------------------------ collaborators
    @property
    def client(self) -> OpenSubtitlesClient:
        if self._client is None:
            from services.opensubtitles import build_opensubtitles_client
            self._client = build_opensubtitles_client(config=self._config)
        return self._client

    @property
    def library(self):
        if self._library is None:
            from services.library import build_library_service
            self._library = build_library_service(self._config)
        return self._library

    # ------------------------------------------------------------------- attach
    def attach(self, *, item_id: str, file_id: int, language: str,
               display_title: str = "", subtitle_id: str = "",
               replace_existing: bool = False,
               allow_upload: bool = True) -> AttachResult:
        """Deliver one OpenSubtitles file to *item_id* and re-read the track list.

        ``replace_existing=False`` (the default) reuses an existing same-language
        sidecar and returns it without spending a download — the dedupe rule from
        trap 8. ``replace_existing=True`` is the explicit "use a different subtitle"
        path, and even then only a file with our own naming convention is overwritten.
        """
        if not item_id:
            raise ValueError("attach() needs an item_id")
        language = (language or "en").strip().lower()
        sid = subtitle_id or f"os:{file_id}"
        video_path = self.library.item_path(item_id)
        sidecar = sidecar_path_for(video_path, language) if video_path else ""

        # --- dedupe: an existing sidecar for this language is already our delivery
        # `.is_file()` — not `.exists()`: a path that exists but is not a regular file
        # is not a subtitle we can reuse (and a directory there must fall through to
        # the write/upload path so the failure is reported honestly). Caught by test.
        if sidecar and Path(sidecar).is_file() and not replace_existing:
            logger.info("subtitle for %s (%s) already present at %s — reusing",
                        item_id, language, sidecar)
            return AttachResult(item_id=item_id, language=language, subtitle_id=sid,
                                display_title=display_title or Path(sidecar).name,
                                file_name=Path(sidecar).name, sidecar_path=sidecar,
                                delivered="sidecar", reused=True,
                                tracks=self._tracks(item_id),
                                remaining=self._client.last_quota() if self._client else None)

        # --- bytes: only now, so a repeat request never spends a download
        got: DownloadedSubtitle = self.client.download(file_id)
        text, encoding = decode_subtitle(got.content)
        if not looks_like_subtitle_text(text):
            raise UnsupportedFormatError(
                f"{got.file_name} does not look like a subtitle file "
                "(it may be an error page or an unsupported format)")

        delivered, written_path = "", ""
        if sidecar:
            try:
                write_atomic(sidecar, text)
                written_path, delivered = sidecar, "sidecar"
                logger.info("wrote sidecar subtitle %s (%d bytes, %s → utf-8)",
                            sidecar, len(got.content), encoding)
            except OSError as e:
                # An unwritable mount is a real state (media outside the api's mounts);
                # degrade to the server upload rather than failing the request.
                logger.warning("could not write sidecar %s (%s) — trying upload", sidecar, e)

        if not delivered and allow_upload:
            if self.library.upload_subtitle(item_id, got.file_name, got.content,
                                            language=language, format=got.extension):
                delivered = "upload"
                logger.info("uploaded subtitle %s to item %s", got.file_name, item_id)

        if not delivered:
            raise UnsupportedFormatError(
                "could not deliver the subtitle: no writable sidecar path and the "
                "server upload was refused")

        tracks = self._tracks(item_id)
        return AttachResult(item_id=item_id, language=language, subtitle_id=sid,
                            display_title=display_title or got.file_name,
                            file_name=got.file_name, sidecar_path=written_path,
                            delivered=delivered, reused=False, tracks=tracks,
                            remaining=got.remaining)

    # ------------------------------------------------------------------ reading
    def _tracks(self, item_id: str, *, retries: int = 3, delay: float = 0.4) -> List[dict]:
        """Refresh the ITEM and return its subtitle tracks (never a library scan).

        ⚠ MEASURED LIVE 2026-09-12: indexing is not instantaneous. Reading the track
        list immediately after an upload can return the OLD list (or nothing) — the
        same failure shape the Continue-Watching work hit, where the server's answer
        is briefly stale rather than wrong. So a delivery we just made is given a
        couple of short re-reads before we accept an empty answer; the total wait is
        bounded (~1 s) because the player can always ask again.

        A refresh failure is logged, never raised: the file/upload is the delivery,
        and losing it because a refresh hiccuped would be the wrong trade.
        """
        try:
            self.library.refresh_item(item_id)
        except Exception as e:
            logger.warning("refresh_item(%s) failed: %s", item_id, e)
        tracks: List[dict] = []
        for attempt in range(1, max(1, retries) + 1):
            try:
                info = self.library.playback_info(item_id)
                tracks = list((info or {}).get("subtitles") or [])
            except Exception as e:
                logger.warning("playback_info(%s) after attach failed: %s", item_id, e)
                tracks = []
            if tracks or attempt == max(1, retries):
                break
            time.sleep(delay)
        return tracks

    # -------------------------------------------------------------------- local
    def local_tracks(self, item_id: str) -> List[dict]:
        """The item's current tracks without touching OpenSubtitles (read-only).

        This is what Phase 3's merged endpoint starts from: local embedded/on-disk
        subtitles must keep working exactly as they do today.
        """
        try:
            info = self.library.playback_info(item_id)
        except Exception as e:
            logger.warning("playback_info(%s) failed: %s", item_id, e)
            return []
        return list((info or {}).get("subtitles") or [])


def search_keywords(context: dict) -> dict:
    """The OpenSubtitles search kwargs for an item, by the plan's §3.2 priority.

    ``tmdb_id`` → ``imdb_id`` → ``title`` (+``year``, and for an episode
    ``season``/``episode``). Two decisions worth stating:

    * An EPISODE is searched by its SERIES title + season/episode, never by the
      episode's own tmdb id — that id identifies the episode, not the show, and the API
      keys TV searches by parent title/season/episode. Measured live 2026-09-12:
      ``Chernobyl`` S1E1 → 19 results, and his library's episodes carry no provider ids
      at all, so this is the path that actually gets used.
    * ``year`` is only sent when the server reports one (ProductionYear); a wrong year
      narrows a search that would otherwise have found the right release.
    """
    context = context or {}
    kind = str(context.get("type") or "").lower()
    if kind == "episode":
        keywords: dict = {}
        title = str(context.get("series_name") or context.get("name") or "").strip()
        if title:
            keywords["title"] = title
        for key in ("year", "season", "episode"):
            if context.get(key) is not None:
                keywords[key] = context[key]
        return keywords
    if context.get("tmdb_id"):
        return {"tmdb_id": context["tmdb_id"]}
    if context.get("imdb_id"):
        return {"imdb_id": str(context["imdb_id"])}
    keywords = {}
    if context.get("name"):
        keywords["title"] = str(context["name"])
    if context.get("year"):
        keywords["year"] = context["year"]
    return keywords


def resolve_active_track(tracks: List[dict], *, display_title: str = "", language: str = "",
                         subtitle_id: str = "") -> Optional[int]:
    """Resolve a STORED subtitle identity to a CURRENT track index (plan §3.6).

    Stream indices are POSITIONAL: adding or removing any track (which our own
    download does) shifts every index after it. So we persist identity — provider +
    subtitle id + language + release title — and resolve the index at playback time:

    1. the exact ``display_title`` (release) match wins;
    2. otherwise the first track in the same language;
    3. otherwise ``None``: apply NOTHING and let the user pick. Never silently
       substitute a different subtitle for the one they chose.
    """
    if not tracks:
        return None
    wanted = (display_title or "").strip().lower()
    if wanted:
        for track in tracks:
            if str(track.get("name") or "").strip().lower() == wanted:
                return track.get("index")
    # Language comparison goes through the 639-1 ↔ 639-2 normaliser: the store holds
    # OpenSubtitles' "en" while the track reports ffprobe's "eng", and a literal
    # comparison would fail to match an English subtitle to an English track.
    lang = normalise_language(language)
    if lang:
        for track in tracks:
            if normalise_language(track.get("language") or "") == lang:
                return track.get("index")
    return None


def usage_key(subtitle_id: str) -> str:
    """The usage counter's key for a subtitle identity (``os:123456`` → ``123456``).

    The plan's store shape keys usage by the provider's numeric file id; a stored
    ``subtitle_id`` carries a provider prefix, so it is stripped here and both forms
    resolve to the same counter. A pure helper (not a store method) because the
    ranking and the response builder both need it, and neither should import the store.
    """
    text = str(subtitle_id or "")
    if ":" in text:
        text = text.split(":", 1)[1]
    return text


def count_for(counts: Dict[str, int], subtitle_id: str) -> int:
    """Our usage count for a subtitle, tolerant of how the map was keyed.

    ⚠ The store's ``usage_counts()`` returns ``{"os:123": n}`` while the raw usage map
    is keyed ``{"123": n}`` — a lookup that assumed ONE of those forms silently returned
    0 for every row, which is a ranking that appears to work and never does. Both forms
    (and a bare numeric id) resolve here. Caught by test.
    """
    counts = counts or {}
    numeric = usage_key(subtitle_id)
    for key in (str(subtitle_id or ""), numeric, f"os:{numeric}"):
        if key and key in counts:
            try:
                return int(counts[key] or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def rank_results(results: List, counts: Dict[str, int]) -> List:
    """Order subtitle results: OUR usage count first, then the provider's popularity.

    Plan criterion 8: a subtitle this user has picked before is a better default than
    one with more global downloads. Ties fall back to ``download_count``, then to the
    stable identity so the order never depends on dict iteration.
    """
    def key(row):
        sid = getattr(row, "subtitle_id", None) or (row or {}).get("subtitle_id", "")
        return (-count_for(counts, sid),
                -int(getattr(row, "download_count", None)
                     or (row or {}).get("download_count", 0) or 0),
                str(sid))
    return sorted(results, key=key)


# ------------------------------------------------------------------ the auto-pick
# SUBTITLE_AUTOPICK_PLAN §2. His decision, 2026-09-21: the api chooses and applies the
# top-ranked subtitle ONCE per title, on first play, behind a global switch, a per-title
# `Off` and a per-AUDIO-language exclusion — and never for a hearing-impaired track.
#
# ⚠ Everything below is a PURE rule: no store, no network, no Jellyfin. The route composes
# them, and that is what lets a test prove the ORDER too (a blocked title must not spend a
# search).

#: Used when `.env` names no language at all. His decision 3 is "the first entry of the
#: configured list", so this is only reachable on an empty list.
AUTO_PICK_FALLBACK_LANGUAGE = "en"


def auto_pick_language(languages=None) -> str:
    """The ONE language the auto-pick searches in — the first entry of the configured list.

    ⚠ Deliberately NOT derived per item (not the audio language, not the last pick): his
    decision 3 chose the predictable rule. ``OPENSUBTITLES_LANGUAGES`` stays the single
    source, so changing it in `.env` changes the auto-pick with no stored state to migrate.
    """
    for raw in (languages or []):
        code = normalise_language(str(raw or ""))
        if code:
            return code
    return AUTO_PICK_FALLBACK_LANGUAGE


def normalise_auto_pick_settings(raw) -> dict:
    """The stored setting, in one shape, whatever was in the file.

    * ``auto_pick`` (bool) — **defaults to ON**, which is his decision 1. A stored
      ``false`` is the global off switch.
    * ``auto_pick_skip_audio`` (list of ISO codes) — his decision 2's third clause: a title
      whose AUDIO is in one of these languages is never auto-picked. Empty by default.
      ⚠ Codes are normalised through :func:`normalise_language` so ``English``/``eng``/``en``
      all mean ``en`` — a skip list that silently failed to match would read as the switch
      being ignored.
    """
    raw = raw if isinstance(raw, dict) else {}
    skip = raw.get("auto_pick_skip_audio")
    codes: List[str] = []
    if isinstance(skip, (list, tuple, set)):
        for item in skip:
            code = normalise_language(str(item or ""))
            if code and code not in codes:
                codes.append(code)
    return {
        "auto_pick": bool(raw.get("auto_pick", True)),
        "auto_pick_skip_audio": codes,
    }


def has_local_track_in(tracks, language: str) -> bool:
    """Does the item already HAVE a subtitle in this language, of its own?

    His decision 1's trigger, and criterion 9: what the film already has is never
    second-guessed — a downloaded subtitle may only fill a gap.
    ⚠ Compared through :func:`normalise_language`, because Jellyfin reports ``eng`` while
    OpenSubtitles speaks ``en`` (the mismatch this whole feature would silently miss).
    """
    want = normalise_language(language)
    if not want:
        return False
    for track in (tracks or []):
        if normalise_language(str((track or {}).get("language") or "")) == want:
            return True
    return False


def auto_pick_candidate(results, *, language: str, counts=None, allow_sdh: bool = False):
    """The subtitle the auto-pick would take — or ``None``.

    ⚠⚠ **IT IS THE FIRST ROW OF THE SAME RANKING THE PANEL DRAWS** (:func:`rank_results`),
    filtered to the language and to non-SDH. That is not tidiness: it is what makes the
    badge the panel shows and the subtitle the api applies **incapable of disagreeing**.
    His decision 4 excludes hearing-impaired tracks (they are often the most downloaded,
    and they carry sound descriptions); ``allow_sdh`` exists so that rule is a parameter a
    test can falsify rather than a hardcoded absence.
    """
    want = normalise_language(language)
    pool = [row for row in (results or [])
            if normalise_language(str(getattr(row, "language", "") or "")) == want
            and (allow_sdh or not bool(getattr(row, "hearing_impaired", False)))]
    ranked = rank_results(pool, counts or {})
    return ranked[0] if ranked else None


def auto_pick_basis(candidate, counts=None) -> str:
    """Why THIS row is the pick: ``used-before`` or ``most-downloaded``.

    The two facts the badge renders. ⚠ They are genuinely different claims: our usage count
    outranks the provider's number in the ranking, so a row can be first for a reason that
    has nothing to do with popularity, and saying "most downloaded" about it would be false.
    """
    if candidate is None:
        return ""
    if count_for(counts or {}, getattr(candidate, "subtitle_id", "")) > 0:
        return "used-before"
    return "most-downloaded"


def auto_pick_blocked(*, settings, stored_preference, tracks, audio_language: str,
                      language: str) -> str:
    """The gates BEFORE any network call — ``""`` when none of them blocks.

    ⚠⚠ **THIS HALF EXISTS SO A BLOCKED TITLE COSTS NOTHING.** Every answer here is
    knowable locally (the store, the item's own tracks, the setting), so the route can
    return the reason without asking OpenSubtitles anything — which is both the honest
    order and the cheap one.

    ⚠ A stored **disabled** record counts as a choice: his decision 2's per-title `Off`
    must beat the auto-pick, or "off" would re-arm on the next play.
    """
    s = normalise_auto_pick_settings(settings)
    if not s["auto_pick"]:
        return "disabled"
    if stored_preference:
        # ⚠ TWO DIFFERENT FACTS, TWO DIFFERENT SENTENCES. "You already chose one" is wrong
        # (and unhelpfully vague) for a title the viewer turned subtitles OFF on — the
        # disabled record is a choice all the same (his decision 2's per-title Off).
        if stored_preference.get("disabled"):
            return "title_off"
        return "already_chosen"
    if has_local_track_in(tracks, language):
        return "has_local_track"
    code = normalise_language(audio_language)
    if code and code in s["auto_pick_skip_audio"]:
        return "audio_excluded"
    return ""


def auto_pick_shortfall(*, remaining, candidate) -> str:
    """The gates that need the search's own answer — ``""`` when the pick may go ahead.

    ⚠ ``remaining is None`` is NOT the same as zero: with an API key and no login, the
    allowance is only reported on a download, so "unknown" means the api cannot promise
    the download will succeed. His decision 1 is explicit — *no attempt* — and the client
    turns ``quota_unknown`` into the one line that fixes it (*add OPENSUBTITLES_USERNAME /
    PASSWORD*), because a silent no-op would read as a broken feature.
    """
    if remaining is None:
        return "quota_unknown"
    try:
        if int(remaining) <= 0:
            return "quota_exhausted"
    except (TypeError, ValueError):
        return "quota_unknown"
    if candidate is None:
        return "no_candidate"
    return ""


#: Every reason the auto-pick can decline, with the sentence the clients render. ⚠ One
#: vocabulary, one place: the api answers with the CODE and the clients never invent copy.
AUTO_PICK_REASONS = {
    "apply": "Auto-subtitles applied the most downloaded result",
    "disabled": "Auto-subtitles is off",
    "already_chosen": "You have already chosen a subtitle for this title",
    "title_off": "Subtitles are off for this title",
    "has_local_track": "This title already has its own subtitle in that language",
    "audio_excluded": "This title's language is excluded from auto-subtitles",
    "not_configured": "OpenSubtitles is not configured",
    "no_search_terms": "This item has no title to search subtitles with",
    "unavailable": "OpenSubtitles could not be reached — nothing was applied",
    "quota_unknown": "Download count unknown — sign in to OpenSubtitles to enable auto-subtitles",
    "quota_exhausted": "No OpenSubtitles downloads left today",
    "no_candidate": "No subtitle in that language was found",
}


def merge_subtitle_rows(tracks: List[dict], remote: List, *, counts=None,
                        active_index: Optional[int] = None,
                        active_subtitle_id: Optional[str] = None,
                        last_used: Optional[Dict[str, str]] = None) -> List[dict]:
    """One list for the player panel: the item's LOCAL tracks, then remote results.

    Local (embedded/on-disk) tracks come first and unchanged — criterion 9: existing
    subtitles keep working exactly as they do today. Remote rows carry our usage count
    and are ranked by it; only local rows carry a stream ``index``, because a remote
    subtitle has no index until it is downloaded and attached.

    EXACTLY ONE row is marked ``active``, and it is the row that REPRESENTS the user's
    choice — the OpenSubtitles result they picked, identified by ``active_subtitle_id``.
    MEASURED LIVE 2026-09-12: the delivered track is only ever named
    "English - SUBRIP - External", so ticking the local track instead leaves the row the
    user actually clicked looking unselected ("it says downloaded but the round box is
    empty") while an unfamiliar row lights up beside it. When a remote identity is
    stored, the local track it resolved to is that same subtitle — a delivery of it, not
    a second choice — so it is deliberately NOT ticked as well. With no remote identity
    (the user picked one of the item's own tracks), ``active_index`` still does the job.
    """
    counts = counts or {}
    last_used = last_used or {}
    rows: List[dict] = []
    for t in tracks or []:
        rows.append({
            "subtitle_id": "",
            "file_id": None,
            "provider": "local",
            "language": str(t.get("language") or ""),
            "display_title": str(t.get("name") or ""),
            "index": t.get("index"),
            "used_count": 0,
            "last_used": "",
            "download_count": 0,
            "hearing_impaired": False,
            "format": "",
            "vendor_format": "",
            "year": None,
            "active": (active_index is not None
                       and t.get("index") == active_index
                       and not active_subtitle_id),
            "local": True,
        })
    for r in rank_results(remote or [], counts):
        sid = r.subtitle_id
        rows.append({
            "subtitle_id": sid,
            # The provider's own file id, so a client can ask for this exact subtitle
            # without parsing our identity format ("os:<file_id>"). Read tolerantly:
            # a row built without it must not break the whole list.
            "file_id": getattr(r, "file_id", None),
            "provider": r.provider,
            "language": r.language,
            "display_title": r.display_title,
            "index": None,
            "used_count": count_for(counts, sid),
            "last_used": last_used.get(sid, "") or last_used.get(usage_key(sid), ""),
            "download_count": r.download_count,
            "hearing_impaired": r.hearing_impaired,
            "format": r.format,
            "vendor_format": r.vendor_format,
            "year": r.year,
            # See the docstring: the user's own choice is the row that gets the tick.
            "active": bool(active_subtitle_id and sid == active_subtitle_id),
            "local": False,
        })
    return rows


def normalise_language(value: str) -> str:
    """A canonical two-letter language key for COMPARISON (``eng``/``EN`` → ``en``).

    Necessary because the two sides speak different standards: OpenSubtitles returns
    639-1 (``en``), while a media server reports whatever ffprobe/its scanner stored —
    usually 639-2/B (``eng``, ``hin``, ``tam``). Comparing them literally would fail
    to match an English track to an English subtitle, which is the exact case the
    auto-apply path depends on.

    Most 639-2 codes map by their two-letter prefix (``eng``→``en``, ``hin``→``hi``);
    the ones where that prefix is WRONG (German ``ger``, French ``fre``…) are in the
    table below.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    if not text:
        return ""
    if "-" in text or "_" in text:                     # pt-BR / zh_CN → pt / zh
        text = text.replace("_", "-").split("-", 1)[0]
    if len(text) == 3:
        return _ISO639_2_EXCEPTIONS.get(text, text[:2])
    if len(text) > 3:                                  # "english", or a stray label
        return _ISO639_2_EXCEPTIONS.get(text[:3], text[:2])
    return text
