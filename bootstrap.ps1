# ============================================================================
# OLD NAME - the entry point is now .\rkm-cinema.ps1
#
# Folded into `rkm-cinema.ps1 deploy` on 2026-09-13 (nothing it did changed - the
# whole deploy body moved there, verbatim, so there is only ONE implementation to
# keep correct). This forwarder exists ONLY so notes, shortcuts, docs and scheduled
# tasks written against the old name keep working instead of dying with
# "not recognized as a command".
#
#   .\bootstrap.ps1              ->  .\rkm-cinema.ps1 deploy
#   .\bootstrap.ps1 -NoBackup    ->  .\rkm-cinema.ps1 deploy -NoBackup
#
# Deliberately NOT [CmdletBinding()]: raw $args are forwarded verbatim, so switches
# reach the real script unchanged.
#
# ASCII only - PowerShell 5.1 misreads UTF-8 without a BOM.
# ============================================================================

$Rest = @()
if ($args.Count -ge 1) { $Rest = $args }

Write-Host "bootstrap.ps1 is now 'rkm-cinema.ps1 deploy' - forwarding ..." -ForegroundColor DarkGray
& "$PSScriptRoot\rkm-cinema.ps1" deploy @Rest
exit $LASTEXITCODE
