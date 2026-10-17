# InCad for FreeCAD on Windows (UNTESTED build): copies the "InCad" folder next to this script into FreeCAD's
# user Mod folder. A previous InCad there is moved to "InCad-backups" first (outside Mod, so FreeCAD does not
# load it). Nothing else is changed; FreeCAD's own installation is only read.
#
#   install.bat
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 [-FreeCAD <folder or FreeCADCmd.exe>] [-ModDir <Mod folder>]
param([string]$FreeCAD = "", [string]$ModDir = "")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $here "InCad"
$logDir = Join-Path $env:LOCALAPPDATA "InCad"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "install.log"

function Say([string]$text) {
    Write-Host $text
    Add-Content -Path $log -Value ("{0}  {1}" -f (Get-Date -Format s), $text)
}

function Fail([string]$text) {
    Write-Host ""
    Write-Host ("ERROR: " + $text) -ForegroundColor Red
    Add-Content -Path $log -Value ("{0}  ERROR: {1}" -f (Get-Date -Format s), $text)
    Write-Host ("Details: " + $log)
    exit 1
}

function Find-FreeCADCmd {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($FreeCAD) {
        if (Test-Path -LiteralPath $FreeCAD -PathType Leaf) {
            $candidates.Add($FreeCAD)
        } else {
            $candidates.Add((Join-Path $FreeCAD "bin\FreeCADCmd.exe"))
            $candidates.Add((Join-Path $FreeCAD "FreeCADCmd.exe"))
        }
    } else {
        $keys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
                  "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                  "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
        foreach ($k in $keys) {
            Get-ItemProperty $k -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName -like "FreeCAD*" -and $_.InstallLocation } |
                Sort-Object DisplayName -Descending |
                ForEach-Object { $candidates.Add((Join-Path $_.InstallLocation.Trim('"') "bin\FreeCADCmd.exe")) }
        }
        foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {
            if ($root -and (Test-Path -LiteralPath $root)) {
                Get-ChildItem -LiteralPath $root -Directory -Filter "FreeCAD*" -ErrorAction SilentlyContinue |
                    Sort-Object Name -Descending |
                    ForEach-Object { $candidates.Add((Join-Path $_.FullName "bin\FreeCADCmd.exe")) }
            }
        }
    }
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c -PathType Leaf) { return (Resolve-Path -LiteralPath $c).Path }
    }
    return $null
}

Say "InCad install (UNTESTED Windows build) from $here"
if (-not (Test-Path -LiteralPath (Join-Path $source "InitGui.py"))) {
    Fail "No InCad\InitGui.py next to this script. Run install.bat from the unzipped folder, not from inside the zip."
}
if (Get-Process -Name "FreeCAD" -ErrorAction SilentlyContinue) {
    Fail "FreeCAD is running. Quit FreeCAD (save your work first), then run the install again."
}

$probe = @{}
$cmd = Find-FreeCADCmd
if ($cmd) {
    Say "FreeCADCmd: $cmd"
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("incad-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        # throwaway settings (-u): the user's FreeCAD settings are never touched. "Continue": in Windows
        # PowerShell a line FreeCADCmd writes to stderr would otherwise stop the script.
        $ErrorActionPreference = "Continue"
        $result = Join-Path $tmp "probe.txt"
        $env:INCAD_PROBE_OUT = $result
        $env:PYTHONDONTWRITEBYTECODE = "1"
        $out = & $cmd -u (Join-Path $tmp "user.cfg") (Join-Path $here "freecad_probe.py") 2>&1 | Out-String
        if (Test-Path -LiteralPath $result) {
            foreach ($line in (Get-Content -LiteralPath $result -Encoding UTF8)) {
                if ($line -match "^(\w+)=(.*)$") { $probe[$Matches[1]] = $Matches[2].Trim() }
            }
        }
    } catch {
        $out = ""
        Say ("FreeCADCmd did not run: " + $_.Exception.Message)
    } finally {
        $ErrorActionPreference = "Stop"
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($probe.Count -eq 0) { Say "FreeCADCmd gave no answer. Its output:"; Say $out }
    foreach ($k in @("freecad", "python", "system", "home", "userdata", "missing")) {
        if ($probe.ContainsKey($k)) { Say ("  {0}: {1}" -f $k, $probe[$k]) }
    }
    if ($probe.ContainsKey("freecad") -and -not $probe["freecad"].StartsWith("1.1")) {
        Say ("WARNING: InCad is made for FreeCAD 1.1; this is FreeCAD " + $probe["freecad"] + ".")
    }
    if ($probe.ContainsKey("missing") -and $probe["missing"] -ne "none") {
        Say ("WARNING: FreeCAD modules not found: " + $probe["missing"] + " (some InCad tools will not work).")
    }
} else {
    Say "FreeCAD was not found (looked in the registry, Program Files and AppData\Local\Programs)."
    Say "  If it is somewhere else: install.bat -FreeCAD ""D:\Apps\FreeCAD 1.1"""
}

if (-not $ModDir) {
    if ($probe.ContainsKey("mod")) {
        $ModDir = $probe["mod"]
    } else {
        $ModDir = Join-Path $env:APPDATA "FreeCAD\v1-1\Mod"
        Say "Using FreeCAD 1.1's usual add-on folder (could not ask FreeCAD)."
    }
}
$ModDir = $ModDir.TrimEnd("\", "/")
Say "Add-on folder: $ModDir"
New-Item -ItemType Directory -Force -Path $ModDir | Out-Null

$target = Join-Path $ModDir "InCad"
if (Test-Path -LiteralPath $target) {
    $backups = Join-Path (Split-Path -Parent $ModDir) "InCad-backups"
    New-Item -ItemType Directory -Force -Path $backups | Out-Null
    $backup = Join-Path $backups ("InCad-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    try {
        Move-Item -LiteralPath $target -Destination $backup
    } catch {
        Fail ("Could not move the old InCad out of the way (" + $_.Exception.Message + "). Is a file of it open?")
    }
    Say "The previous InCad was moved to: $backup"
}

try {
    Copy-Item -LiteralPath $source -Destination $target -Recurse
    Get-ChildItem -LiteralPath $target -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
} catch {
    Fail ("Copying failed: " + $_.Exception.Message)
}
if (-not (Test-Path -LiteralPath (Join-Path $target "InitGui.py"))) { Fail "The copy has no InitGui.py: $target" }

Set-Content -Path (Join-Path $logDir "installed.txt") -Value $ModDir  # for uninstall.ps1
Say ""
Say "Installed: $target"
Say "Start FreeCAD and choose InCad in the workbench selector."
Say ("InCad's log: " + (Join-Path $logDir "InCad.log") + " (send it with any problem report)")
exit 0
