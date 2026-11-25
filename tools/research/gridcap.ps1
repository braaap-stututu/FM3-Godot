# A debug-server capture of the frozen CrownJewel test grid with game-numbered constants and the vertex constants
# (2026-11-25): every draw's pixel and vertex constants, e.g. the paint's per-car shCubeMapDampnerLight (vc37).
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\gridcap.ps1 [-Out <folder>]
# Output: <Out>\grid.png (the game's picture) and <Out>\cap.log (the capture's log lines).
param([string]$Out = "$env:TEMP\gridcap")
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:REGPU_NO_PACKED_CONSTANTS = '1'; $env:REGPU_TRACE_VC = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    Start-Sleep 3
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
Remove-Item Env:REGPU_NO_PACKED_CONSTANTS, Env:REGPU_TRACE_VC, Env:FM3_GRID_TEST, Env:FM3_MINIMIZED -ErrorAction SilentlyContinue
if (-not $frozen) { throw "the grid did not freeze (see $log)" }
. "$r\tools\fm3ctl.ps1"
Start-Sleep 3
Fm3 "shot $Out\grid.png" | Out-Null
$before = (Get-Content $log).Count
Fm3 'capture' | Out-Null
Fm3 'wait 3' | Out-Null
Start-Sleep 8
@(Get-Content $log | Select-Object -Skip $before) | Set-Content "$Out\cap.log"
"captured $((Get-Content "$Out\cap.log").Count) lines into $Out"
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
