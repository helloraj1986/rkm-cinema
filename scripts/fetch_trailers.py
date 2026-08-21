#!/usr/bin/env python3
"""Fetch YouTube trailer IDs from TMDB using API key."""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List

def load_env():
    env_path = Path("/workspace/media/.env")
    env_vars = {}
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                env_vars[key] = val
    return env_vars

def get_tmdb_trailer(tmdb_id: int, media_type: str, api_key: str) -> Optional[Dict]:
    """Fetch trailer from TMDB using Bearer token."""
    if media_type == "movie":
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos"
    else:
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/videos"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        videos = data.get('results', [])
        
        # Find YouTube trailer
        for video in videos:
            if (video.get('type') == 'Trailer' and 
                video.get('site') == 'YouTube' and
                video.get('official') == True):
                return {
                    'id': video.get('key'),
                    'name': video.get('name'),
                    'site': video.get('site')
                }
        
        # Fallback to any trailer
        for video in videos:
            if video.get('type') == 'Trailer' and video.get('site') == 'YouTube':
                return {
                    'id': video.get('key'),
                    'name': video.get('name'),
                    'site': video.get('site')
                }
        
        return None
        
    except Exception as e:
        print(f"Error fetching TMDB {tmdb_id}: {e}")
        return None

def validate_youtube_id(video_id: str) -> bool:
    """Validate YouTube video exists via oEmbed."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def fetch_and_validate_trailers():
    env_vars = load_env()
    tmdb_api_key = env_vars.get("TMDB_API_KEY")
    
    if not tmdb_api_key:
        print("ERROR: TMDB_API_KEY not found in /workspace/media/.env")
        print("Please add TMDB_API_KEY to .env file")
        return
    
    watchlist_path = Path("/workspace/media/watchlist.json")
    with open(watchlist_path) as f:
        watchlist = json.load(f)
    
    pending = watchlist.get('pending', [])
    updated_count = 0
    
    print(f"Checking {len(pending)} entries for trailers...")
    
    for entry in pending:
        title = entry.get('title')
        tmdb_id = entry.get('tmdbId')
        is_series = entry.get('isSeries', False)
        current_trailer = entry.get('trailerId')
        
        if not tmdb_id:
            print(f"  Skip {title}: No TMDB ID")
            continue
        
        # Validate existing trailer
        if current_trailer:
            if validate_youtube_id(current_trailer):
                print(f"  ✓ {title}: Trailer valid ({current_trailer})")
                continue
            else:
                print(f"  ✗ {title}: Existing trailer invalid ({current_trailer})")
        
        # Fetch from TMDB
        print(f"  Fetching trailer for {title} from TMDB...")
        trailer = get_tmdb_trailer(tmdb_id, 'tv' if is_series else 'movie', tmdb_api_key)
        
        if trailer:
            video_id = trailer['id']
            if validate_youtube_id(video_id):
                entry['trailerId'] = video_id
                entry['trailerTitle'] = trailer['name']
                updated_count += 1
                print(f"    ✓ Updated trailer: {video_id} - {trailer['name']}")
            else:
                print(f"    ✗ TMDB trailer invalid: {video_id}")
        else:
            print(f"    ✗ No trailer found on TMDB")
    
    if updated_count > 0:
        watchlist['updated'] = '2026-08-19T19:00:00'
        with open(watchlist_path, 'w') as f:
            json.dump(watchlist, f, indent=2)
        print(f"\nUpdated {updated_count} trailers")
        
        # Rebuild dashboard
        import subprocess
        subprocess.run(['python3', 'scripts/rebuild_dashboard.py'], cwd='/workspace/media/watchlist')
    else:
        print("\nNo trailers updated")

if __name__ == "__main__":
    fetch_and_validate_trailers()
