# RKM Cinema — Smart Download Selection Implementation

## Status: PARTIALLY COMPLETED

## Completed Tasks

### Task 1: Quality Definition Size Limits ✅
Updated all quality definitions with proper size limits:
- **720p qualities**: 800-1500MB (preferred: 1000-1200MB)
- **1080p qualities**: 1500-2000MB (preferred: 1700-1900MB)
- **Bluray-1080p**: Capped at 1800MB (forced limit)
- **Remux-1080p**: 1800-2000MB (preferred: 1900MB)

### Task 2: Minimum Seeders Requirement ✅
Updated 4 out of 7 indexers to require minimum 5 seeders:
- seedpool (API) (Prowlarr): 5 seeders
- The Pirate Bay (Prowlarr): 5 seeders
- TheRARBG (Prowlarr): 5 seeders
- YTS (Prowlarr): 5 seeders

Note: 3 indexers failed due to rate limiting from Prowlarr (429 errors).

### Task 3: Quality Profile Configuration ✅
- Quality profile ID 3 (HD-720p) configured
- Profile restricts to 720p/1080p qualities only
- Upgrade not allowed (prevents automatic upgrades to larger files)

## Partially Completed

### Task 4: Indexer Configuration
- 4/7 indexers updated with minimum seeders
- 3 indexers need manual update through Radarr UI due to rate limiting

## Remaining Tasks

### Task 5: Manual Configuration Needed
The following need to be configured through the Radarr UI:

1. **Complete indexer updates**:
   - BitSearch (Prowlarr): Set minimumSeeders to 5
   - kickasstorrents.ws (Prowlarr): Set minimumSeeders to 5
   - RuTracker.RU (Prowlarr): Set minimumSeeders to 5

2. **Create release profile** (if needed):
   - Navigate to Settings → Release Profiles
   - Create a new profile with minimum seeders requirement
   - Apply to all movies

3. **Test the configuration**:
   - Search for a movie and verify file sizes are within limits
   - Verify download starts with good seeders
   - Monitor download speeds and completion

## Configuration Summary

### Current Settings
- **Quality Profile**: HD-720p (Profile ID 3)
- **Quality Limits**: 720p/1080p only, 800MB-2000MB
- **Minimum Seeders**: 5 (for 4/7 indexers)
- **Download Client**: qBittorrent
- **Upgrade Allowed**: False

### Expected Behavior
- Movies will download as 720p or 1080p quality
- File sizes should be between 800MB and 2GB
- Downloads should have at least 5 seeders
- No automatic upgrades to larger files

## Next Steps
1. Complete manual indexer updates through Radarr UI
2. Test with a sample movie download
3. Verify file sizes and download speeds
4. Adjust settings if needed based on results
