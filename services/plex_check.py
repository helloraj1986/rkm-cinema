"""Plex check service - Verify media is not already in Plex before adding to watchlist."""

import re
import requests
from typing import Tuple, Dict, List
from dataclasses import dataclass
import xml.etree.ElementTree as ET

@dataclass
class PlexMedia:
    title: str
    year: int
    type: str  # 'movie' or 'show'
    rating_key: str = None


class PlexCheckService:
    """Service to check if media exists in Plex library."""
    
    def __init__(self, plex_url: str, plex_token: str):
        self.plex_url = plex_url.rstrip('/')
        self.plex_token = plex_token
        self._movies_cache: Dict[Tuple[str, int], PlexMedia] = None
        self._shows_cache: Dict[Tuple[str, int], PlexMedia] = None
        
    def _fetch_section(self, section_id: int, section_type: str) -> List[PlexMedia]:
        """Fetch all media from a Plex section."""
        url = f"{self.plex_url}/library/sections/{section_id}/all"
        params = {
            'X-Plex-Token': self.plex_token
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            media_list = []
            
            # Find all Video elements (movies) and Directory elements (shows)
            if section_type == 'movie':
                for video in root.findall('.//Video'):
                    title = video.get('title')
                    year = int(video.get('year', 0))
                    rating_key = video.get('ratingKey')
                    
                    if title and year:
                        media_list.append(PlexMedia(
                            title=title,
                            year=year,
                            type=section_type,
                            rating_key=rating_key
                        ))
            else:  # show
                for directory in root.findall('.//Directory'):
                    # Only check show directories
                    if directory.get('type') == 'show':
                        title = directory.get('title')
                        year = int(directory.get('year', 0))
                        rating_key = directory.get('ratingKey')
                        
                        if title and year:
                            media_list.append(PlexMedia(
                                title=title,
                                year=year,
                                type=section_type,
                                rating_key=rating_key
                            ))
            
            return media_list
            
        except Exception as e:
            print(f"Error fetching section {section_id}: {e}")
            return []
    
    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        title = title.lower().strip()
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title
    
    def build_cache(self, movie_section_id: int = 13, show_section_id: int = 15):
        """Build cache of Plex media."""
        print("Building Plex cache...")
        
        movies = self._fetch_section(movie_section_id, 'movie')
        shows = self._fetch_section(show_section_id, 'show')
        
        self._movies_cache = {
            (self._normalize_title(m.title), m.year): m 
            for m in movies
        }
        
        self._shows_cache = {
            (self._normalize_title(s.title), s.year): s 
            for s in shows
        }
        
        print(f"Cached {len(self._movies_cache)} movies, {len(self._shows_cache)} shows")
    
    def check_exists(self, title: str, year: int, is_series: bool = False) -> bool:
        """Check if media exists in Plex."""
        if self._movies_cache is None or self._shows_cache is None:
            raise ValueError("Cache not built. Call build_cache() first")
        
        normalized = self._normalize_title(title)
        key = (normalized, year)
        
        if is_series:
            return key in self._shows_cache
        else:
            return key in self._movies_cache
    
    def check_exists_fuzzy(self, title: str, year: int, is_series: bool = False) -> Tuple[bool, str]:
        """Check with fuzzy matching and return match reason."""
        if self._movies_cache is None or self._shows_cache is None:
            raise ValueError("Cache not built. Call build_cache() first")
        
        normalized = self._normalize_title(title)
        key = (normalized, year)
        
        cache = self._shows_cache if is_series else self._movies_cache
        
        if key in cache:
            media = cache[key]
            return True, f"Exact match: {media.title} ({media.year})"
        
        # Try fuzzy matching on title only
        for (cached_title, cached_year), media in cache.items():
            if cached_year == year and normalized in cached_title:
                return True, f"Fuzzy match: {media.title} ({media.year})"
        
        return False, "Not found"
    
    def get_plex_title(self, title: str, year: int, is_series: bool = False) -> str:
        """Get actual Plex title if exists."""
        if self._movies_cache is None or self._shows_cache is None:
            return None
        
        normalized = self._normalize_title(title)
        key = (normalized, year)
        cache = self._shows_cache if is_series else self._movies_cache
        
        media = cache.get(key)
        return media.title if media else None


# Test the service
if __name__ == "__main__":
    from pathlib import Path
    
    env_path = Path("/workspace/media/.env")
    env_vars = {}
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                env_vars[key] = val
    
    service = PlexCheckService(
        plex_url=env_vars.get("PLEX_URL", "http://192.168.65.254:32400"),
        plex_token=env_vars.get("PLEX_TOKEN", "")
    )
    
    service.build_cache()
    
    # Test some titles
    test_titles = [
        ("Dune: Part Two", 2024, False),
        ("Oppenheimer", 2023, False),
        ("The Bear", 2022, True),
        ("Succession", 2018, True),
        ("Better Call Saul", 2015, True),
        ("The Boys", 2019, True),
        ("The Mandalorian", 2019, True),
        ("Dark", 2017, True),
    ]
    
    print("\nChecking titles:")
    for title, year, is_series in test_titles:
        exists, reason = service.check_exists_fuzzy(title, year, is_series)
        print(f"  {title} ({year}): {'EXISTS' if exists else 'NOT FOUND'} - {reason}")
