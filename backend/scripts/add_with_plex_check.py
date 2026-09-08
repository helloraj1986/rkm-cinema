"""Add media to watchlist with Plex validation."""

import json
from pathlib import Path
from services.plex_check import PlexCheckService
from config.settings import get_config

def load_env():
    """Load env vars."""
    env_path = Path("/workspace/media/.env")
    env_vars = {}
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                env_vars[key] = val
    return env_vars

def add_to_watchlist_with_plex_check(new_entries: list, dry_run: bool = True):
    """Add entries to watchlist only if not in Plex."""
    
    env_vars = load_env()
    service = PlexCheckService(
        plex_url=env_vars.get("PLEX_URL", "http://192.168.65.254:32400"),
        plex_token=env_vars.get("PLEX_TOKEN", "")
    )
    
    service.build_cache()
    
    watchlist_path = Path("/workspace/media/watchlist.json")
    with open(watchlist_path) as f:
        watchlist = json.load(f)
    
    pending = watchlist.get('pending', [])
    existing_ids = {e.get('imdbId') for e in pending}
    
    added = []
    skipped_plex = []
    skipped_duplicate = []
    
    for entry in new_entries:
        imdb_id = entry.get('imdbId')
        
        # Check duplicate
        if imdb_id in existing_ids:
            skipped_duplicate.append(entry['title'])
            continue
        
        # Check Plex
        exists, reason = service.check_exists_fuzzy(
            entry['title'], 
            entry['year'], 
            entry.get('isSeries', False)
        )
        
        if exists:
            skipped_plex.append((entry['title'], reason))
            continue
        
        added.append(entry)
    
    print(f"Added: {len(added)}")
    print(f"Skipped (Plex): {len(skipped_plex)}")
    print(f"Skipped (duplicate): {len(skipped_duplicate)}")
    
    if skipped_plex:
        print("\nSkipped Plex entries:")
        for title, reason in skipped_plex:
            print(f"  - {title}: {reason}")
    
    if skipped_duplicate:
        print("\nSkipped duplicates:")
        for title in skipped_duplicate:
            print(f"  - {title}")
    
    if not dry_run:
        watchlist['pending'].extend(added)
        watchlist['updated'] = '2026-08-19T18:00:00'
        
        with open(watchlist_path, 'w') as f:
            json.dump(watchlist, f, indent=2)
        
        print(f"\nWatchlist updated with {len(added)} new entries")
    
    return added, skipped_plex, skipped_duplicate


# Example usage
if __name__ == "__main__":
    # Example entries (would normally come from recommendation engine)
    test_entries = [
        {
            "title": "Dune: Part Two",
            "year": 2024,
            "imdbId": "tt15239678",
            "isSeries": False
        },
        {
            "title": "The Bear",
            "year": 2022,
            "imdbId": "tt10157119",
            "isSeries": True
        },
        {
            "title": "Succession",
            "year": 2018,
            "imdbId": "tt1187043",
            "isSeries": True
        }
    ]
    
    add_to_watchlist_with_plex_check(test_entries, dry_run=True)
