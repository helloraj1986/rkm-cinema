#!/usr/bin/env python3
"""Validate and fix YouTube trailer IDs."""

import json
from pathlib import Path
import requests

def validate_youtube_id(video_id: str) -> bool:
    """Validate YouTube video exists via oEmbed."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def main():
    watchlist_path = Path("/workspace/media/watchlist.json")
    with open(watchlist_path) as f:
        watchlist = json.load(f)
    
    pending = watchlist.get('pending', [])
    
    print(f"Validating {len(pending)} entries...")
    print("=" * 80)
    
    all_valid = True
    invalid_entries = []
    
    for entry in pending:
        title = entry.get('title')
        trailer_id = entry.get('trailerId')
        
        if not trailer_id:
            print(f"⚠ {title}: No trailer ID")
            invalid_entries.append((title, None))
            all_valid = False
            continue
        
        is_valid = validate_youtube_id(trailer_id)
        
        if is_valid:
            print(f"✓ {title}: {trailer_id}")
        else:
            print(f"✗ {title}: {trailer_id} - INVALID")
            invalid_entries.append((title, trailer_id))
            all_valid = False
    
    print("=" * 80)
    
    if all_valid:
        print("✓ All trailers valid!")
    else:
        print(f"\n✗ Found {len(invalid_entries)} invalid/missing trailers")
        print("\nInvalid entries:")
        for title, trailer_id in invalid_entries:
            if trailer_id:
                print(f"  - {title}: {trailer_id} (invalid)")
            else:
                print(f"  - {title}: No trailer ID")

if __name__ == "__main__":
    main()
