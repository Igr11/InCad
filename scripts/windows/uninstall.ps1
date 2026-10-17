# Removes the InCad test build from FreeCAD's user Mod folder: the folder is moved to "InCad-backups" (next to Mod),
# not deleted, so nothing is lost. InCad's log and FreeCAD's settings stay.
#
#   uninstall.bat
#   powershell -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1 [-ModDir <Mod folder>]
param([string]$ModDir = "")

$ErrorActionPreference = "Stop"
$installed = Join-Path $env:LOCALAPPDATA "InCad\installed.txt"  # written by install.ps1
if (-not $ModDir -and (Test-Path -LiteralPath $installed)) { $ModDir = (Get-Content -LiteralPath $installed -TotalCount 1).Trim() }
if (-not $ModDir) { $ModDir = Join-Path $env:APPDATA "FreeCAD\v1-1\Mod" }
$ModDir = $ModDir.TrimEnd("\", "/")
$target = Join-Path $ModDir "InCad"

if (Get-Process -Name "FreeCAD" -ErrorAction SilentlyContinue) {
    Write-Host "ERROR: FreeCAD is running. Quit FreeCAD first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "InCad is not installed in $ModDir"
    Write-Host "  (installed elsewhere? uninstall.bat -ModDir ""<the Mod folder>"")"
    exit 0
}
$backups = Join-Path (Split-Path -Parent $ModDir) "InCad-backups"
New-Item -ItemType Directory -Force -Path $backups | Out-Null
$backup = Join-Path $backups ("InCad-removed-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
try {
    Move-Item -LiteralPath $target -Destination $backup
} catch {
    Write-Host ("ERROR: could not move $target (" + $_.Exception.Message + ")") -ForegroundColor Red
    exit 1
}
Write-Host "InCad removed from FreeCAD. The folder was moved to: $backup"
Write-Host "Delete $backups yourself when you no longer need it."
exit 0
