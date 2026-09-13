# ============================================================================
# RKM stack - THE one script. Everything you ever need to run is in here.
#
#   .\rkm-cinema.ps1 status                 what is running, drives wired, scan state
#   .\rkm-cinema.ps1 apply                  make the running stack match THIS folder
#                                           (re-render .env, rebuild + restart api/web)
#   .\rkm-cinema.ps1 deploy [-NoBackup]     apply + Jellyfin provisioner (first run,
#                                           new libraries or keys)
#   .\rkm-cinema.ps1 auth                   is sign-in required right now?
#   .\rkm-cinema.ps1 auth on                require sign-in for everything (the switch)
#   .\rkm-cinema.ps1 auth off               back to open - THE RECOVERY if you lock out
#   .\rkm-cinema.ps1 logs [api|web|jellyfin]
#   .\rkm-cinema.ps1 backup                 archive Jellyfin state now (keeps newest 7)
#   .\rkm-cinema.ps1 restore [-Archive <file>] [-Yes]
#   .\rkm-cinema.ps1 schedule               install the nightly 04:00 state backup
#   .\rkm-cinema.ps1 diagnose               why a library / episode / watch-state looks wrong
#   .\rkm-cinema.ps1 reset-admin-password [-DryRun] [-Name <account>]
#                                           locked out of the ADMINISTRATOR account: set a
#                                           new password using the stack's own API key
#   .\rkm-cinema.ps1 help                   this list
#
# WHICH ONE DO I WANT?
#   You edited .env, or you pulled new code            ->  apply
#   You want the app to stop being open to everyone    ->  auth on
#   You are setting the stack up / changed libraries   ->  deploy
#   You are locked out of the app                      ->  auth off
#   Something is wrong                                 ->  status, then diagnose
#
# DO NOT run raw `docker compose` commands for these. `apply` is what recreates the
# containers so a changed .env actually takes effect - editing .env alone does nothing,
# because a container reads its environment when it STARTS.
#
# Why `apply` instead of a full rebuild: it re-renders .rkm.env, rebuilds only api and
# web (Docker caches unchanged layers), and skips the Jellyfin provisioner - which
# matters, because the provisioner can cancel an in-flight library scan.
#
# The real work lives in render_config.py, tools\*.py and scripts\*.ps1 (the last only
# for backup/restore). Those are internals: this script is the only one you run.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "apply", "deploy", "auth", "logs", "backup", "restore",
                 "schedule", "diagnose", "reset-admin-password", "help")]
    [string]$Command = "help",

    # The second word, used by `auth` only: on | off.
    [Parameter(Position = 1)]
    [string]$Value = "",

    # `logs` takes an optional service name.
    [string]$Service = "",

    [string]$Archive,
    # -Name: the administrator's account name. Only needed when the server has more
    # than one enabled administrator (it may have been renamed - never assume "admin").
    [string]$Name,
    # -DryRun: read-only. Names the account it WOULD reset, changes nothing.
    [switch]$DryRun,
    # -Yes: skip the typed confirmation on restore.
    [switch]$Yes,
    # -NoBackup: skip the pre-deploy state archive.
    [switch]$NoBackup
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Project = "rkm-bundled"
$AuthKey = "RKM_AUTH_REQUIRED"
# A route that requires a session once the switch is on. Asking THIS what it answers is
# the honest question: it reports what the api actually does, not what .env intended.
$ProbeRoute = "/api/library/folders"

function Get-Python {
    foreach ($exe in @("python", "python3", "py")) {
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Require-Python {
    $py = Get-Python
    if (-not $py) { throw "python not found on PATH - install Python 3, then re-run." }
    return $py
}

function Write-Head($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

function Get-DashboardPort {
    $dp = "8124"
    try {
        $found = Select-String -Path .env -Pattern "^RKM_DASHBOARD_PORT=(.*)$" -ErrorAction SilentlyContinue
        if ($found) { $dp = $found.Matches[0].Groups[1].Value.Trim() }
    } catch {}
    return $dp
}

function Get-AuthEnvValue {
    $found = Select-String -Path .env -Pattern "^$AuthKey=(.*)$" -ErrorAction SilentlyContinue
    if ($found) { return $found.Matches[0].Groups[1].Value.Trim() }
    return ""
}

function Test-SignInRequired {
    # "401" (required), "200" (open), or "" (could not ask).
    $dp = Get-DashboardPort
    try {
        $code = (& curl.exe -s -o NUL -w "%{http_code}" "http://localhost:$dp$ProbeRoute" | Out-String).Trim()
        # curl prints 000 when nothing answered. That is "could not ask", NOT a status - without
        # this it would be reported as a mismatch against the expected 401/200.
        if ($code -and $code -ne "000") { return $code }
    } catch {}
    return ""
}

function Invoke-Render {
    $py = Require-Python
    Write-Host "Re-rendering .env -> .rkm.env ..."
    & $py "$PSScriptRoot\render_config.py"
    if ($LASTEXITCODE -ne 0) { throw "render_config.py failed - the stack was NOT touched." }
}

function Invoke-Apply {
    # Make the RUNNING stack match this folder: config first, then code, then recreate.
    Invoke-Render
    Write-Host "Rebuilding + restarting api and web ..."
    # NOTE: raw `docker compose` calls with an explicit $LASTEXITCODE check, NOT a helper
    # function. A helper would have to take the flag-like arguments ("-d", "--build"), and
    # PowerShell binds anything that looks like a parameter name BEFORE a remainder
    # parameter - so `Compose up -d --build api web` fails with "parameter cannot be found
    # that matches parameter name 'd'". Every command names $Project directly instead.
    & docker compose -p $Project up -d --build api web
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed - see the output above." }
    Write-Host ""
    Write-Host "Applied. Dashboard: http://localhost:$(Get-DashboardPort)/" -ForegroundColor Green
    Write-Host "Jellyfin, its config and your media were not touched." -ForegroundColor DarkGray
}

function Invoke-Deploy {
    # The full path (the old bootstrap.ps1). The pre-deploy state archive is kept, because
    # this is the command that rebuilds EVERYTHING - the one situation where a safety copy
    # of the volumes is worth having. -NoBackup skips it.
    if (-not $NoBackup) {
        Write-Host "Archive of the stack state before rebuilding ..." -ForegroundColor Cyan
        & "$PSScriptRoot\scripts\backup-rkm-state.ps1"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "State backup skipped or failed (see above) - continuing." -ForegroundColor Yellow
        }
    }

    Invoke-Render

    Write-Host "Starting api + web + jellyfin (project $Project) ..."
    & docker compose -p $Project up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed - see the output above." }

    $dp = Get-DashboardPort
    Write-Host "Waiting for API health ..."
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $s = (Invoke-WebRequest -Uri "http://localhost:$dp/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode
            if ($s -eq 200) { $ready = $true; break }
        } catch {}
        Start-Sleep -Seconds 2
    }
    if (!$ready) { Write-Host "API not healthy after 120s - check: .\rkm-cinema.ps1 logs api" -ForegroundColor Yellow }

    Write-Host "Running the Jellyfin provisioner (admin + API key + libraries) ..."
    & docker compose -p $Project --profile provision run --rm --build provisioner
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Provisioner had issues (see above). Jellyfin may need one manual setup at http://localhost:8098/web" -ForegroundColor Yellow
    }

    # `up -d api` alone does NOT recreate an unchanged container; force-recreate so a
    # fresh process re-reads the runtime config (Config() is cached per process).
    Write-Host "Restarting api to load the runtime config ..."
    & docker compose -p $Project up -d --force-recreate api
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed - see the output above." }

    Write-Host ""
    Write-Host "Stack ready:" -ForegroundColor Green
    Write-Host "  Dashboard:  http://localhost:$dp/"
    Write-Host "  Jellyfin:   http://localhost:8098/web"
    Write-Host "  API health: http://localhost:$dp/api/health"
}

function Show-Auth {
    # Reported from BEHAVIOUR: what the running api answers to a request with no session.
    # A .env value that has not been applied yet is intent, not fact - and confusing the
    # two is exactly what made this switch feel unpredictable.
    Write-Head "Sign-in requirement"
    $fromFile = Get-AuthEnvValue
    if ($fromFile) {
        Write-Host ("  .env says        : {0}" -f $fromFile)
    } else {
        Write-Host "  .env says        : (not set - treated as false)"
    }

    $code = Test-SignInRequired
    if ($code -eq "401") {
        Write-Host ("  the running api  : 401 on {0} - sign-in IS required" -f $ProbeRoute) -ForegroundColor Green
        Write-Host ""
        Write-Host "  Everything except /api/health and the sign-in routes needs a session." -ForegroundColor Green
    } elseif ($code -eq "200") {
        Write-Host ("  the running api  : 200 on {0} - the app is OPEN" -f $ProbeRoute) -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Anyone who can reach the app is served as the stack's own credential," -ForegroundColor Yellow
        Write-Host "  signed out included. Turn it on:  .\rkm-cinema.ps1 auth on" -ForegroundColor Yellow
    } else {
        Write-Host "  the running api  : no answer - is the stack up?  (.\rkm-cinema.ps1 status)" -ForegroundColor Yellow
    }
}

function Set-Auth($want) {
    if ($want -ne "on" -and $want -ne "off") {
        throw "usage: .\rkm-cinema.ps1 auth on   |   .\rkm-cinema.ps1 auth off"
    }
    $word = "false"
    if ($want -eq "on") { $word = "true" }

    $py = Require-Python
    # ONE tested editor for .env (backup taken, comments preserved, refused if the value
    # would break the file) rather than a text munge here, where nothing could test it.
    & $py "$PSScriptRoot\tools\set_env_value.py" $AuthKey $word
    if ($LASTEXITCODE -ne 0) { throw "could not update .env - nothing was applied." }

    Write-Host ""
    Write-Host "Applying (this is the step that makes it take effect) ..." -ForegroundColor Cyan
    Invoke-Apply

    # PROVE it: ask the api, not the file. A switch that reports success without checking
    # is how "it says changed but nothing changes" happens.
    Write-Host ""
    $expected = if ($want -eq "on") { "401" } else { "200" }
    $code = Test-SignInRequired
    if ($code -eq $expected) {
        if ($want -eq "on") {
            Write-Host "Confirmed: a request with no session is refused (401)." -ForegroundColor Green
            Write-Host "Open http://localhost:$(Get-DashboardPort)/ and sign in as your administrator account." -ForegroundColor Green
        } else {
            Write-Host "Confirmed: the app is open again (200 with no session)." -ForegroundColor Yellow
        }
    } elseif ($code) {
        Write-Host "Applied, but the api answers $code, not $expected - run '.\rkm-cinema.ps1 status'." -ForegroundColor Red
    } else {
        Write-Host "Could not confirm (the api did not answer) - run '.\rkm-cinema.ps1 status'." -ForegroundColor Yellow
    }
    if ($want -eq "on") {
        Write-Host "Locked out?  .\rkm-cinema.ps1 auth off" -ForegroundColor DarkGray
    }
}

function Show-Status {
    Write-Head "Containers"
    docker compose -p $Project ps

    Write-Head "State volumes (these hold watch state / libraries)"
    docker volume ls --format "{{.Name}}" | Select-String "^$Project"

    Show-Auth

    Write-Head "App + Jellyfin health"
    $py = Get-Python
    if (-not $py) {
        Write-Host "   python not found on PATH - skipping the deep check" -ForegroundColor Yellow
        Write-Host "   (install Python 3, or read the dashboard at http://localhost:$(Get-DashboardPort)/)"
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

    # This REPLACES the current Jellyfin state. Literally the last thing you want to do by
    # accident, so it needs a typed confirmation unless -Yes is passed.
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
    $py = Require-Python
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
    $py = Require-Python
    # Not `$args`: that name is PowerShell's own automatic variable.
    $toolArgs = @("$PSScriptRoot\tools\reset_admin_password.py")
    if ($Name) { $toolArgs += @("--name", $Name) }
    if ($DryRun) { $toolArgs += "--dry-run" }
    & $py @toolArgs
}

function Show-Help {
    Write-Host ""
    Write-Host "RKM stack - one script" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\rkm-cinema.ps1 status                 what is running, drives wired, scan state"
    Write-Host "  .\rkm-cinema.ps1 apply                  make the running stack match THIS folder"
    Write-Host "                                          (use after editing .env or pulling code)"
    Write-Host "  .\rkm-cinema.ps1 deploy [-NoBackup]     apply + Jellyfin provisioner (first run,"
    Write-Host "                                          new libraries or keys)"
    Write-Host "  .\rkm-cinema.ps1 auth                   is sign-in required right now?"
    Write-Host "  .\rkm-cinema.ps1 auth on                require sign-in for everything"
    Write-Host "  .\rkm-cinema.ps1 auth off               back to open (THE RECOVERY if you lock out)"
    Write-Host "  .\rkm-cinema.ps1 logs [service]         tail api + web + jellyfin (or one of them)"
    Write-Host "  .\rkm-cinema.ps1 backup                 archive Jellyfin state now (keeps newest 7)"
    Write-Host "  .\rkm-cinema.ps1 restore                -Archive <file>  (default: newest archive)"
    Write-Host "  .\rkm-cinema.ps1 schedule               install the nightly 04:00 backup task"
    Write-Host "  .\rkm-cinema.ps1 diagnose               investigate a library, episode or watch-state"
    Write-Host "  .\rkm-cinema.ps1 reset-admin-password [-DryRun] [-Name <admin>]"
    Write-Host ""
    Write-Host "  Dashboard: http://localhost:$(Get-DashboardPort)/   Jellyfin: http://localhost:8098/web"
    Write-Host "  Full runbook: docs\OPERATIONS.md"
    Write-Host ""
}

switch ($Command) {
    "status"   { Show-Status }
    "apply"    { Invoke-Apply }
    "deploy"   { Invoke-Deploy }
    "auth"     {
        if ($Value) { Set-Auth $Value } else { Show-Auth }
    }
    "logs"     {
        if ($Service) { docker compose -p $Project logs --tail 60 $Service }
        else { docker compose -p $Project logs --tail 40 api web jellyfin }
    }
    "backup"   { & "$PSScriptRoot\scripts\backup-rkm-state.ps1" }
    "restore"  { Invoke-Restore }
    "schedule" { & "$PSScriptRoot\scripts\install-backup-task.ps1" }
    "diagnose" { Invoke-Diagnose }
    "reset-admin-password" { Invoke-ResetAdminPassword }
    "help"     { Show-Help }
}
