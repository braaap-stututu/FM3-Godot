# Every car object at the same moments of a race (2026-11-27; for the HUD's race position / laps): boots the test grid
# with the race AI driving the player's car too, and at -Times seconds after the start dumps -Size bytes of every car
# object (the log's "live: car XXXXXXXX" addresses) one after another (<Out>\cars.txt: moment, car, hex). A race
# position shows as an offset where the cars' values are a permutation of 0..7 or 1..8 at every moment.
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\allcars.ps1 -Out <dir> [-Times '5,25,45'] [-Size 16384]
param([string]$Out, [string]$Times = '5,25,45,70', [int]$Size = 16384)
$ErrorActionPreference = 'Continue'
$r = (Resolve-Path "$PSScriptRoot\..\..\..\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"; $t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'; $env:FM3_AI_PLAYER = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) { Start-Sleep 3; if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break } }
foreach ($v in 'FM3_GRID_TEST', 'FM3_MINIMIZED', 'FM3_LIVE', 'FM3_AI_PLAYER') { Set-Item "Env:$v" '' }
if (-not $frozen) { throw 'no grid' }
. "$r\tools\fm3ctl.ps1"
$cars = [regex]::Matches((Get-Content $log -Raw), 'live: car ([0-9A-F]{8}) at') | % { $_.Groups[1].Value } | Select-Object -Unique
"cars $($cars -join ' ')" | Set-Content "$Out\info.txt"
Remove-Item "$Out\cars.txt" -ErrorAction SilentlyContinue
# moment 0: the frozen grid before the start (the starting order)
function DumpAll($tag) {
    foreach ($c in $cars) {
        $a = [Convert]::ToUInt32($c, 16); $hex = ''
        for ($k = 0; $k -lt $Size / 4096; $k++) { $hex += (Fm3 ("peek {0:X8} 4096" -f ($a + 4096 * $k))) -replace '.*"hex":"([0-9A-F]*)".*', '$1' }
        "$tag $c $hex" | Add-Content "$Out\cars.txt"
    }
}
DumpAll 'grid'
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
$sw = [Diagnostics.Stopwatch]::StartNew()
foreach ($t in ($Times -split ',')) {
    while ($sw.Elapsed.TotalSeconds -lt [double]$t) { Start-Sleep -Milliseconds 200 }
    Fm3 'env FM3_FREEZE_TIME 1' | Out-Null   # (the same moment for every car)
    Start-Sleep 1
    Fm3 "shot $Out\t$t.png" | Out-Null
    DumpAll "t$t"
    Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done"
