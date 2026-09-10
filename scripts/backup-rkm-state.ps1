# ============================================================================
# RKM bundled stack - back up the state that lives in Docker volumes.
#
#   run:  .\scripts\backup-rkm-state.ps1
#
# Jellyfin keeps its state (users, watched flags, playback positions, library
# definitions, Jellyfin API keys, metadata) in the NAMED VOLUME mounted at
# /config, so it already survives container restarts, rebuilds and
# `docker compose down`. It does NOT survive `down -v`, and it would LOOK lost if
# compose ever ran under a different project name (Docker creates fresh empty
# volumes in that case). This script is the safety net for both.
#
# Steps:
#   1. discover the project's ACTUAL volume names (never assume them),
#   2. stop jellyfin so the SQLite state is quiesced while it is read,
#   3. tar config + shared into <BackupPath>\rkm-state-<stamp>.tar.gz,
#   4. start jellyfin again,
#   5. verify the archive (entry count + size) and prune all but the newest N.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Project    = "rkm-bundled",
    [string]$BackupPath = "D:\RKM_BACKUPS",
    [int]$Keep          = 7,
    [switch]$NoStop
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Write-Step($m) { Write-Host "== $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "   $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "   $m" -ForegroundColor Yellow }
function Fail($m)       { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

# --- Docker present? -------------------------------------------------------
docker version --format "x" | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is not running." }

# --- Discover the real volume names ----------------------------------------
# Never hardcode these: a volume is project-scoped (<project>_<volume>), so the
# actual name depends on how compose was invoked. Guessing wrong here is exactly
# how you would back up nothing (or restore into a fresh empty volume).
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
        Fail "no volume ending in '_$suffix' exists. Has the stack ever run? Check: docker volume ls"
    }
    Fail "several volumes end in '_$suffix' ($($loose -join ', ')) - refusing to guess which holds your state."
}

Write-Step "Locating state volumes"
$configVol = Resolve-Volume "jellyfin-config"
$sharedVol = Resolve-Volume "rkm_shared"
Write-Ok "jellyfin state : $configVol"
Write-Ok "shared runtime : $sharedVol"

if (-not (Test-Path $BackupPath)) { New-Item -ItemType Directory -Force -Path $BackupPath | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveName = "rkm-state-$stamp.tar.gz"
$archivePath = Join-Path $BackupPath $archiveName

# --- Quiesce, archive, resume ---------------------------------------------
$stopped = $false
if (-not $NoStop) {
    Write-Step "Stopping jellyfin (so the database is quiesced while it is read)"
    docker compose -p $Project stop jellyfin | Out-Null
    $stopped = $true
}
else {
    Write-Warn2 "-NoStop given: the archive may capture a half-written database."
}

try {
    Write-Step "Archiving to $archivePath"
    docker run --rm `
        -v "${configVol}:/config:ro" `
        -v "${sharedVol}:/shared:ro" `
        -v "${BackupPath}:/backup" `
        alpine:3 sh -c "tar czf /backup/$archiveName -C / config shared"
    if ($LASTEXITCODE -ne 0) { Fail "tar failed (exit $LASTEXITCODE) - nothing was written." }
}
finally {
    if ($stopped) {
        Write-Step "Starting jellyfin again"
        docker compose -p $Project start jellyfin | Out-Null
    }
}

# --- Verify ---------------------------------------------------------------
if (-not (Test-Path $archivePath)) { Fail "archive missing after the run: $archivePath" }
$sizeMb = [math]::Round((Get-Item $archivePath).Length / 1MB, 2)
$entries = 0
try {
    $out = @(docker run --rm -v "${BackupPath}:/backup:ro" alpine:3 sh -c "tar tzf /backup/$archiveName | wc -l")
    $entries = [int]($out | Select-Object -First 1)
}
catch { $entries = 0 }
Write-Step "Verifying archive"
Write-Ok "size    : $sizeMb MB"
Write-Ok "entries : $entries"
if ($entries -lt 10 -or $sizeMb -lt 0.05) {
    Fail "archive looks empty ($entries entries, $sizeMb MB) - do not trust it."
}

# --- Prune ---------------------------------------------------------------
$all = @(Get-ChildItem -Path $BackupPath -Filter "rkm-state-*.tar.gz" | Sort-Object LastWriteTime -Descending)
if ($all.Count -gt $Keep) {
    foreach ($old in ($all | Select-Object -Skip $Keep)) {
        Remove-Item $old.FullName -Force
        Write-Ok "pruned $($old.Name)"
    }
}

Write-Step "Done"
Write-Ok "$([math]::Min($all.Count, $Keep)) archive(s) kept in $BackupPath (newest: $archiveName)"
Write-Ok "restore with: .\scripts\restore-rkm-state.ps1 -Archive `"$archivePath`""
exit 0
