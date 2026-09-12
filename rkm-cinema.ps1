# ============================================================================
# RKM stack - ONE command, so nothing has to be remembered.
#
#   .\rkm-cinema.ps1 status     what is running, are the drives wired, is a scan on?
#   .\rkm-cinema.ps1 deploy     build/refresh the stack (same as .\bootstrap.ps1)
#   .\rkm-cinema.ps1 backup     archive the Jellyfin state now
#   .\rkm-cinema.ps1 restore    restore from an archive (-Archive <file>, else newest)
#   .\rkm-cinema.ps1 schedule   install the nightly 04:00 state backup
#   .\rkm-cinema.ps1 diagnose   why a library / episode / watch-state looks wrong
#   .\rkm-cinema.ps1 reset-admin-password   locked out? set a new admin password (-DryRun to look)
#   .\rkm-cinema.ps1 logs       last lines from api + web + jellyfin
#   .\rkm-cinema.ps1 help       this list
#
# Every one of these is a thin wrapper: the real work lives in bootstrap.ps1,
# scripts\*.ps1 and tools\*.py, so running a wrapper can never diverge from
# running the tool directly. Details: docs\OPERATIONS.md
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "deploy", "backup", "restore", "schedule",
                 "diagnose", "reset-admin-password", "logs", "help")]
    [string]$Command = "help",

    [string]$Archive,
    # -Name: the administrator's account name. Only needed when the server has more
    # than one enabled administrator (it may have been renamed - never assume "admin").
    [string]$Name,
    # -DryRun: read-only. Names the account it WOULD reset, changes nothing.
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Project = "rkm-bundled"

function Get-Python {
    foreach ($exe in @("python", "python3", "py")) {
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Write-Head($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

function Show-Help {
    Write-Host ""
    Write-Host "RKM stack - one command" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\rkm-cinema.ps1 status     what is running, drives wired, scan state"
    Write-Host "  .\rkm-cinema.ps1 deploy     build + refresh the stack (.\bootstrap.ps1)"
    Write-Host "  .\rkm-cinema.ps1 backup     archive Jellyfin state now (keeps newest 7)"
    Write-Host "  .\rkm-cinema.ps1 restore    -Archive <file>  (default: newest archive)"
    Write-Host "  .\rkm-cinema.ps1 schedule   install the nightly 04:00 backup task"
    Write-Host "  .\rkm-cinema.ps1 diagnose   investigate a library, episode or watch-state"
    Write-Host "  .\rkm-cinema.ps1 reset-admin-password [-DryRun] [-Name <admin>]"
    Write-Host "                             locked out of the ADMINISTRATOR account: set a new password"
    Write-Host "                             using the stack's own API key (the old one is not needed)"
    Write-Host "  .\rkm-cinema.ps1 logs       tail api + web + jellyfin"
    Write-Host ""
    Write-Host "  Dashboard: http://localhost:8124/   Jellyfin: http://localhost:8098/web"
    Write-Host "  Full runbook: docs\OPERATIONS.md"
    Write-Host ""
}

function Show-Status {
    Write-Head "Containers"
    docker compose -p $Project ps

    Write-Head "State volumes (these hold watch state / libraries)"
    docker volume ls --format "{{.Name}}" | Select-String "^$Project"

    Write-Head "App + Jellyfin health"
    $py = Get-Python
    if (-not $py) {
        Write-Host "   python not found on PATH - skipping the deep check" -ForegroundColor Yellow
        Write-Host "   (install Python 3, or read the dashboard at http://localhost:8124/)"
        return
    }
    & $py "$PSScriptRoot\tools\rkm_status.py"
}

function Invoke-Restore {
    $target = $Archive
    if (-not $target) {
        $dir = "D:\RKM_BACKUPS"
        if (-not (Test-Path $dir)) { throw "No -Archive given and $dir does not exist." }
        $newest = Get-ChildItem -Path $dir -Filter "rkm-state-*.tar.gz" |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $newest) { throw "No -Archive given and no archive found in $dir." }
        $target = $newest.FullName
        Write-Host "Using newest archive: $target" -ForegroundColor Yellow
    }
    if (-not (Test-Path $target)) { throw "Archive not found: $target" }

    # This REPLACES the current Jellyfin state. Literally the last thing you want
    # to do by accident, so it needs a typed confirmation unless -Yes is passed.
    if (-not $Yes) {
        Write-Host ""
        Write-Host "This will REPLACE the current Jellyfin state (users, watch history," -ForegroundColor Yellow
        Write-Host "libraries) with the contents of:" -ForegroundColor Yellow
        Write-Host "  $target" -ForegroundColor Yellow
        $answer = Read-Host "Type YES to continue"
        if ($answer -ne "YES") { Write-Host "Cancelled."; return }
    }
    & "$PSScriptRoot\scripts\restore-rkm-state.ps1" -Archive $target
}

function Invoke-Diagnose {
    $py = Get-Python
    if (-not $py) { throw "python not found on PATH - needed for the diagnostics." }
    Write-Head "Watch-state + episode classifier (TV Shows)"
    & $py "$PSScriptRoot\tools\diagnose_series_state.py" --show-empty 10
    Write-Host ""
    Write-Host "If this needs a deeper look:" -ForegroundColor Cyan
    Write-Host "  $py tools\diagnose_episode_linkage.py --show ""<show name>"""
    Write-Host "  $py tools\probe_media_files.py --dir ""/media2/TV Shows/<folder>"""
    Write-Host "  $py tools\probe_jellyfin_state.py --library ""TV Shows"" --series 20"
}

function Invoke-ResetAdminPassword {
    # The break-glass (ADMIN_CREDENTIALS_PLAN.md Phase 4). The password is TYPED at the tool's own
    # prompt, never passed here: an argument would sit in your PowerShell history and in the process
    # list. Nothing is changed until you have typed it twice.
    $py = Get-Python
    if (-not $py) { throw "python not found on PATH - needed for the reset." }
    # Not `$args`: that name is PowerShell's own automatic variable.
    $toolArgs = @("$PSScriptRoot\tools\reset_admin_password.py")
    if ($Name) { $toolArgs += @("--name", $Name) }
    if ($DryRun) { $toolArgs += "--dry-run" }
    & $py @toolArgs
}

switch ($Command) {
    "status"   { Show-Status }
    "deploy"   { & "$PSScriptRoot\bootstrap.ps1" }
    "backup"   { & "$PSScriptRoot\scripts\backup-rkm-state.ps1" }
    "restore"  { Invoke-Restore }
    "schedule" { & "$PSScriptRoot\scripts\install-backup-task.ps1" }
    "diagnose" { Invoke-Diagnose }
    "reset-admin-password" { Invoke-ResetAdminPassword }
    "logs"     { docker compose -p $Project logs --tail 40 api web jellyfin }
    "help"     { Show-Help }
}
