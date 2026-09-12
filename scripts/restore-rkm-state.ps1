# ============================================================================
# Restore Jellyfin state + the shared runtime config from an archive made by
# scripts/backup-rkm-state.ps1.
#
#   run:  .\scripts\restore-rkm-state.ps1 -Archive D:\RKM_BACKUPS\rkm-state-20260910-041500.tar.gz
#
# DESTRUCTIVE-ADJACENT, so it is deliberately careful:
#   - verifies the archive BEFORE touching anything,
#   - by default takes a fresh backup of the CURRENT state first (so a restore
#     can itself be undone) - pass -SkipPreBackup to skip,
#   - stops the whole stack while the volumes are written,
#   - EXTRACTS OVER the existing contents (it does not wipe the volumes): a
#     partial extraction can therefore never leave you with an empty /config.
#     Consequence: files created AFTER the backup are not removed. For a
#     recovery (empty or corrupted volume) that is exactly what you want.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$Project = "rkm-bundled",
    [string]$BackupPath = "D:\RKM_BACKUPS",
    [switch]$SkipPreBackup
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Write-Step($m) { Write-Host "== $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "   $m" -ForegroundColor Yellow }
function Fail($m)       { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

docker version --format "x" | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is not running." }

if (-not (Test-Path $Archive)) { Fail "archive not found: $Archive" }
$archiveItem = Get-Item $Archive
$archiveDir = $archiveItem.DirectoryName
$archiveName = $archiveItem.Name

# --- Same discovery as the backup script (never hardcode volume names) -----
function Resolve-Volume([string]$suffix) {
    $exact = "${Project}_$suffix"
    $all = @(docker volume ls --format "{{.Name}}")
    if ($all -contains $exact) { return $exact }
    $loose = @($all | Where-Object { $_ -like "*_$suffix" })
    if ($loose.Count -eq 1) {
        Write-Warn2 "volume '$exact' not found; using '$($loose[0])' instead"
        return $loose[0]
    }
    if ($loose.Count -eq 0) {
        Fail "no volume ending in '_$suffix' exists - create the stack once (.\\bootstrap.ps1) before restoring."
    }
    Fail "several volumes end in '_$suffix' ($($loose -join ', ')) - refusing to guess."
}

Write-Step "Verifying the archive before touching anything"
$listing = @(docker run --rm -v "${archiveDir}:/backup:ro" alpine:3 sh -c "tar tzf /backup/$archiveName")
if ($LASTEXITCODE -ne 0) { Fail "cannot read the archive (not a valid .tar.gz?)" }
$hasConfig = @($listing | Where-Object { $_ -like "config/*" }).Count -gt 0
$hasShared = @($listing | Where-Object { $_ -like "shared/*" }).Count -gt 0
Write-Ok "entries      : $($listing.Count)"
Write-Ok "contains config/ : $hasConfig"
Write-Ok "contains shared/ : $hasShared"
if (-not $hasConfig) { Fail "archive does not contain a config/ tree - that is not a Jellyfin state backup." }

$configVol = Resolve-Volume "jellyfin-config"
$sharedVol = Resolve-Volume "rkm_shared"
Write-Ok "jellyfin state : $configVol"
Write-Ok "shared runtime : $sharedVol"

# --- Optional safety net: back up what we are about to overwrite ----------
if (-not $SkipPreBackup) {
    Write-Step "Backing up the CURRENT state first (so this restore can be undone)"
    & (Join-Path $PSScriptRoot "backup-rkm-state.ps1") -Project $Project -BackupPath $BackupPath
    if ($LASTEXITCODE -ne 0) {
        Fail "pre-restore backup failed - refusing to overwrite a state you cannot get back."
    }
}

# --- Stop the stack, write the volumes, bring it back ---------------------
Write-Step "Stopping the stack (project $Project)"
docker compose -p $Project stop | Out-Null

try {
    Write-Step "Extracting $archiveName into the volumes"
    docker run --rm `
        -v "${configVol}:/config" `
        -v "${sharedVol}:/shared" `
        -v "${archiveDir}:/backup:ro" `
        alpine:3 sh -c "tar xzf /backup/$archiveName -C / && echo extracted"
    if ($LASTEXITCODE -ne 0) { Fail "extraction failed (exit $LASTEXITCODE)." }
}
finally {
    Write-Step "Starting the stack again"
    docker compose -p $Project up -d | Out-Null
}

Write-Step "Done"
Write-Ok "state restored from $archiveName"
Write-Ok "next: hard-refresh the app (Ctrl+Shift+R) and check Continue Watching /"
Write-Ok "      the libraries. Jellyfin sign-in uses the ADMIN ACCOUNT AS IT WAS IN THE BACKUP"
Write-Ok "      (users and their password hashes travel inside /config), NOT whatever .env says:"
Write-Ok "      RKM_JELLYFIN_ADMIN_PASSWORD is only an override and may well be blank."
exit 0
