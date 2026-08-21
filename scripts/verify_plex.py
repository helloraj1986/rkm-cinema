"""Verify current watchlist entries against Plex and clean them up."""

import json
from pathlib import Path
from services.plex_check import PlexCheckService

def load_env():
    env_path = Path("/workspace/media/.env")
    env_vars = {}
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                env_vars[key] = val
    return env_vars

def verify_watchlist():
    env_vars = load_env()
    service = PlexCheckService(
        plex_url=env_vars.get("PLEX_URL"),
        plex_token=env_vars.get("PLEX_TOKEN")
    )
    service.build_cache()
    
    watchlist_path = Path("/workspace/media/watchlist.json")
    with open(watchlist_path) as f:
        watchlist = json.load(f)
    
    pending = watchlist.get('pending', [])
    exists_in_plex = []
    not_in_plex = []
    
    for entry in pending:
        exists, reason = service.check_exists_fuzzy(
            entry['title'],
            entry['year'],
            entry.get('isSeries', False)
        )
        
        if exists:
            exists_in_plex.append((entry, reason))
        else:
            not_in_plex.append(entry)
    
    print(f"Total pending: {len(pending)}")
    print(f"Already in Plex: {len(exists_in_plex)}")
    print(f"Not in Plex: {len(not_in_plex)}")
    
    if exists_in_plex:
        print("\n=== Entries already in Plex (should be removed) ===")
        for entry, reason in exists_in_plex:
            print(f"  - {entry['title']} ({entry['year']}) - {reason}")
    
    print("\n=== Entries not in Plex (valid) ===")
    for entry in not_in_plex[:10]:
        print(f"  - {entry['title']} ({entry['year']})")
    
    if len(not_in_plex) < len(pending):
        print(f"\n*** Found {len(exists_in_plex)} entries already in Plex! ***")
        print("Run with --clean to remove them")
    
    return exists_in_plex, not_in_plex

if __name__ == "__main__":
    import sys
    exists, valid = verify_watchlist()
    
    if '--clean' in sys.argv and exists:
        watchlist_path = Path("/workspace/media/watchlist.json")
        with open(watchlist_path) as f:
            watchlist = json.load(f)
        
        # Remove entries in Plex
        pending = watchlist.get('pending', [])
        ids_to_remove = {e[0]['imdbId'] for e in exists}
        watchlist['pending'] = [e for e in pending if e.get('imdbId') not in ids_to_remove]
        
        with open(watchlist_path, 'w') as f:
            json.dump(watchlist, f, indent=2)
        
        print(f"\nCleaned watchlist. New count: {len(watchlist['pending'])}")
