# Record the game's cameras while the race AI drives the player's car (2026-11-25): boots the CrownJewel test grid
# with FM3_AI_PLAYER=1 and FM3_LIVE=1, lets the race run, and records the stream (tools\camrec.py) once per camera view
# (RB cycles them). Output: <Out>\view<k>.npz (+ a game shot per view). Fit with tools\camfit.py.
param([string]$Out = "$env:TEMP\camrec", [int]$Views = 6, [double]$Seconds = 14)
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'; $env:FM3_AI_PLAYER = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    Start-Sleep 3
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
foreach ($v in 'FM3_GRID_TEST', 'FM3_MINIMIZED', 'FM3_LIVE', 'FM3_AI_PLAYER') { Set-Item "Env:$v" '' }
if (-not $frozen) { throw "the grid did not freeze (see $log)" }
. "$r\tools\fm3ctl.ps1"
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null    # the race starts; the AI drives the player's car
Start-Sleep 6
# The player's car-physics object (live_camera.cpp logs it; FH1's ICarDynamics layout as the lead: controls at +3904,
# gear +2240, speed +3128, wheels from +3936): its first 8 KB every half second while the AI drives, with the time.
$phys = ([regex]::Matches((Get-Content $log -Raw), 'live: player car physics ([0-9A-F]{8})') | Select-Object -Last 1).Groups[1].Value
if ($phys) {
    $dump = @()
    for ($i = 0; $i -lt 30; $i++) {
        $a = [Convert]::ToUInt32($phys, 16)
        $h0 = (Fm3 ("peek {0:X8} 4096" -f $a)) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
        $h1 = (Fm3 ("peek {0:X8} 4096" -f ($a + 4096))) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
        $dump += ("{0:F3} {1}{2}" -f ((Get-Date) - $t0).TotalSeconds, $h0, $h1)
        Start-Sleep -Milliseconds 500
    }
    $dump | Set-Content "$Out\physics_$phys.txt"
    "physics object ${phys}: 30 dumps"
}
Start-Sleep 2
for ($k = 0; $k -lt $Views; $k++) {
    & $py "$g\frame-ir\tools\camrec.py" --seconds $Seconds --out "$Out\view$k.npz"
    Fm3 "shot $Out\view$k.png" | Out-Null
    Fm3 'press RB 500' | Out-Null          # the next camera view
    Start-Sleep 2
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
