# ============================================================================
# OLD NAME - the entry point is now .\rkm-cinema.ps1
#
# Renamed 2026-09-11 (nothing it wraps changed). This forwarder exists ONLY so
# notes, shortcuts or scheduled tasks written against the old name keep working
# instead of dying with "not recognized as a command". Delete it once nothing
# refers to it any more.
#
#   .\rkm.ps1 status      ->  .\rkm-cinema.ps1 status
#
# Deliberately NOT [CmdletBinding()]: raw $args are forwarded verbatim, so
# "restore -Archive <file>" and "-Yes" reach the real script unchanged.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================

$Command = if ($args.Count -ge 1) { [string]$args[0] } else { "help" }
$Rest = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

Write-Host "rkm.ps1 was renamed to rkm-cinema.ps1 - forwarding '$Command' ..." -ForegroundColor DarkGray
& "$PSScriptRoot\rkm-cinema.ps1" $Command @Rest
exit $LASTEXITCODE
