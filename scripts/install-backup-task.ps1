# ============================================================================
# Register (or remove) the nightly backup of the RKM stack state.
#
#   run:  .\scripts\install-backup-task.ps1
#         .\scripts\install-backup-task.ps1 -At 03:30 -Keep 14
#         .\scripts\install-backup-task.ps1 -Remove
#
# The task runs as YOU (not as SYSTEM): Docker Desktop runs in your user session,
# so a system-level task would not see the Docker engine. It uses
# -StartWhenAvailable, so a run missed while the PC was asleep happens as soon as
# it wakes.
#
# This is the scheduled half of the safety net. The other half is bootstrap.ps1,
# which now takes a backup before every rebuild.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================
[CmdletBinding()]
param(
    [string]$At = "04:00",
    [string]$BackupPath = "D:\RKM_BACKUPS",
    [int]$Keep = 7,
    [string]$TaskName = "RKM state backup",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

function Write-Step($m) { Write-Host "== $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "   $m" -ForegroundColor Green }
function Fail($m)       { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

if ($Remove) {
    Write-Step "Removing scheduled task '$TaskName'"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Ok "removed (your existing archives in $BackupPath are untouched)"
    exit 0
}

$script = Join-Path $PSScriptRoot "backup-rkm-state.ps1"
if (-not (Test-Path $script)) { Fail "backup script not found: $script" }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) { Write-Host "   replacing the existing '$TaskName' task" -ForegroundColor Yellow }

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -BackupPath `"$BackupPath`" -Keep $Keep"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Archives the RKM stack Jellyfin state + shared runtime config to $BackupPath" `
    -Force | Out-Null

Write-Step "Registered"
Write-Ok "task      : $TaskName"
Write-Ok "schedule  : daily at $At (runs when you are logged on)"
Write-Ok "archives  : $BackupPath (keeps the newest $Keep)"
Write-Ok "run now   : Start-ScheduledTask -TaskName `"$TaskName`""
Write-Ok "check     : Get-ScheduledTaskInfo -TaskName `"$TaskName`""
Write-Ok "Note: Docker Desktop must be running for a scheduled run to succeed."
exit 0
