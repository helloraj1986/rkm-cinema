"""YouTube service for finding and validating official trailers (no API key).

Searches youtube.com directly and extracts the official trailer's video ID
from the search results page, so no YouTube Data API key is required. The
result is used to build an in-app embedded player (youtube.com/embed/<id>).
"""
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from config.settings import get_config

logger = logging.getLogger("rkm.youtube")

# Regexes to extract the embedded JSON (ytInitialData) from YouTube result pages.
_YT_INITIAL_DATA_RE = re.compile(r"var\s+ytInitialData\s*=\s*({.*?});</script>", re.DOTALL)
# Fallback regexes for individual video renderers.
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_TITLE_RE = re.compile(r'"title":\{"runs":\[\{"text":"(.*?)"\}\]')
_CHANNEL_RE = re.compile(r'"ownerText":\{"runs":\[\{"text":"(.*?)"\}\]')


class YouTubeService:
    """YouTube integration for finding official trailers by scraping results."""

    SEARCH_URL = "https://www.youtube.com/results"

    # Channel-name fragments that strongly indicate an official studio/distributor channel.
    OFFICIAL_CHANNEL_MARKERS = (
        "pictures", "studios", "films", "movies", "entertainment", "official",
        "warner", "universal", "disney", "sony", "paramount", "fox", "searchlight",
        "netflix", "hbo", "max", "showtime", "amazon", "apple tv", "lionsgate",
        "a24", "focus features", "illumination", "dreamworks", "sony pictures",
    )
    # Title indicators that it's a real trailer.
    TRAILER_INDICATORS = ("official trailer", "trailer", "teaser trailer", "official teaser")

    def __init__(self, *, config=None):
        self.config = config if config is not None else get_config()

    # ------------------------------------------------------------------ public API
    def has_youtube(self) -> bool:
        """Scraping requires no API key, so this is always True."""
        return True

    def search_trailer(self, title: str, year: int, is_series: bool = False) -> Optional[Dict[str, Any]]:
        """Search for an official trailer on YouTube by scraping results.

        Returns a dict with trailer_id/trailer_title/channel for embedding, or None.
        """
        if not title:
            return None

        queries = self._build_queries(title, year, is_series)
        for query in queries:
            videos = self._search(query)
            if not videos:
                continue
            best = self._pick_best(videos, title)
            if best:
                logger.info("Chose trailer for %s: %s via YouTube (%s)",
                            title, best["trailer_id"], best["source"])
                return best
        logger.warning("No YouTube trailer found for %s (%s)", title, year)
        return None

    def search_and_enrich(self, title: str, year: int, is_series: bool = False,
                          imdb_id: str = "", tmdb_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Compatibility alias for search_trailer with enrich context."""
        return self.search_trailer(title, year, is_series)

    def validate_trailer(self, trailer_id: str) -> bool:
        """Validate that a YouTube video ID is the correct length/format."""
        if not trailer_id:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", str(trailer_id)))

    def get_embed_url(self, trailer_id: str) -> str:
        """Get an embeddable URL for in-app playback."""
        if self.validate_trailer(trailer_id):
            return f"https://www.youtube.com/embed/{trailer_id}?autoplay=1&rel=0&modestbranding=1&color=white"
        return ""

    def get_trailer_url(self, trailer_id: str) -> str:
        """Get a watch URL for a trailer ID."""
        if self.validate_trailer(trailer_id):
            return f"https://www.youtube.com/watch?v={trailer_id}"
        return ""

    # ------------------------------------------------------------------ internals

    def _build_queries(self, title: str, year: int, is_series: bool) -> List[str]:
        """Build search-query candidates, most specific / official first."""
        kind = "TV series" if is_series else "movie"
        base = title.strip()
        queries = [
            f'"{base}" {year} official trailer',
            f"{base} {year} trailer {kind}",
            f"{base} official trailer",
            f"{base} trailer",
        ]
        seen, out = set(), []
        for q in queries:
            if q not in seen:
                seen.add(q)
                out.append(q)
        return out

    def _search(self, query: str) -> List[Dict[str, Any]]:
        """Scrape the YouTube results page and return candidate videos."""
        params = urllib.parse.urlencode({"search_query": query})
        url = f"{self.SEARCH_URL}?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", "ignore")
        except Exception as e:
            logger.error("YouTube search request failed for %r: %s", query, e)
            return []

        return self._parse_results(html, query)

    def _parse_results(self, html: str, query: str) -> List[Dict[str, Any]]:
        """Parse candidate videos out of the YouTube results HTML."""
        candidates: List[Dict[str, Any]] = []

        # First try the structured ytInitialData blob.
        m = _YT_INITIAL_DATA_RE.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                candidates = self._extract_from_initial_data(data)
            except Exception:
                candidates = []

        # Fallback: coarse regex over raw videoId/title pairs.
        if not candidates:
            ids = _VIDEO_ID_RE.findall(html)
            titles = _TITLE_RE.findall(html)
            channels = _CHANNEL_RE.findall(html)
            # Zip loosely: videoIds and titles appear in mostly the same order.
            for i, vid in enumerate(ids):
                rec = {
                    "videoId": vid,
                    "title": titles[i] if i < len(titles) else "",
                    "channel": channels[i] if i < len(channels) else "",
                    "publishedAt": "",
                    "description": "",
                    "ownerVerified": False,
                }
                if rec["title"] and (rec["channel"] or len(ids) <= 10):
                    candidates.append(rec)

        # De-duplicate by videoId, preserving order.
        seen, unique = set(), []
        for c in candidates:
            vid = c.get("videoId", "")
            if vid and vid not in seen:
                seen.add(vid)
                unique.append(c)
        return unique

    def _extract_from_initial_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Walk the ytInitialData tree for videoRenderer entries from search results."""
        out: List[Dict[str, Any]] = []

        def walk(node: Any, depth: int = 0) -> None:
            if depth > 30 or node is None:
                return
            if isinstance(node, list):
                for item in node:
                    walk(item, depth + 1)
                return
            if isinstance(node, dict):
                vr = node.get("videoRenderer")
                if isinstance(vr, dict) and vr.get("videoId"):
                    snippet = vr.get("title", {}).get("runs", [])
                    title = "".join(r.get("text", "") for r in snippet if isinstance(r, dict))
                    owner = vr.get("ownerText", {}).get("runs", [])
                    channel = "".join(r.get("text", "") for r in owner if isinstance(r, dict)) if owner else ""
                    badges = vr.get("ownerBadges") or []
                    verified = any("badgeStyle" in str(b) for b in badges)
                    meta = vr.get("publishedTimeText", {}).get("simpleText", "")
                    out.append({
                        "videoId": vr["videoId"],
                        "title": title,
                        "channel": channel,
                        "publishedAt": meta,
                        "ownerVerified": verified,
                    })
                for v in node.values():
                    walk(v, depth + 1)

        walk(data)
        return out

    def _pick_best(self, videos: List[Dict[str, Any]], title: str) -> Optional[Dict[str, Any]]:
        """Pick the most likely official trailer from the candidate list."""
        if not videos:
            return None

        t = (title or "").lower()
        t_words = set(re.findall(r"[a-z0-9]+", t))

        def score(v: Dict[str, Any]) -> float:
            s = 0.0
            vtitle = (v.get("title") or "").lower()
            channel = (v.get("channel") or "").lower()

            # Title must relate to the searched title.
            words = set(re.findall(r"[a-z0-9]+", vtitle))
            overlap = len(words & t_words) / max(1, len(t_words)) if t_words else 0
            if overlap < 0.4:
                return -1.0  # unrelated noise

            # Strongly prefer the term "trailer" in the title.
            if "trailer" in vtitle:
                s += 3.0
            if "official" in vtitle:
                s += 1.5
            # Channel looks like a studio/distributor.
            if any(marker in channel for marker in self.OFFICIAL_CHANNEL_MARKERS):
                s += 2.0
            # Verified badge.
            if v.get("ownerVerified"):
                s += 1.0
            # Penalize common fan/noise keywords.
            for bad in ("reaction", "review", "analysis", "explained", "recap", "ending",
                        "how to", "top 10", "parody", "music video", "song", "supercut"):
                if bad in vtitle:
                    s -= 3.0
            return s

        scored = [(score(v), v) for v in videos]
        scored = [x for x in scored if x[0] >= 0]
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        if best_score <= 0:
            return None
        return {
            "trailer_id": best["videoId"],
            "trailer_title": (best.get("title") or "Official Trailer")[:200],
            "channel_title": best.get("channel", ""),
            "published_at": best.get("publishedAt", ""),
            "description": "",
            "thumbnail": f"https://i.ytimg.com/vi/{best['videoId']}/hqdefault.jpg",
            "owner_verified": bool(best.get("ownerVerified")),
            "source": "youtube_scrape",
        }
