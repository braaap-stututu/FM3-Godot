# The game's own telemetry screen against the car-physics object (2026-11-25): boots the test grid with the race AI
# driving the player's car, lets it race 14 s, opens the telemetry screen (d-pad UP), cycles its pages (RIGHT) and per
# page takes a game shot and dumps the player's physics object (8 KB) at the same moment (<Out>\phys.txt).
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\telepage.ps1 -Out <dir>
param([string]$Out)
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
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
Start-Sleep 14
$phys = ([regex]::Matches((Get-Content $log -Raw), 'live: player car physics ([0-9A-F]{8})') | Select-Object -Last 1).Groups[1].Value
Fm3 'press UP 150' | Out-Null; Start-Sleep 1.5
foreach ($dir in 'RIGHT') {
  for ($k = 0; $k -lt 7; $k++) {
    if ($k -gt 0) { Fm3 "press $dir 150" | Out-Null }; Start-Sleep 1.5
    Fm3 "shot $Out\$dir-$k.png" | Out-Null
    $a = [Convert]::ToUInt32($phys, 16)
    $h0 = (Fm3 ("peek {0:X8} 4096" -f $a)) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    $h1 = (Fm3 ("peek {0:X8} 4096" -f ($a + 4096))) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    "$dir-$k $h0$h1" | Add-Content "$Out\phys.txt"
  }
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done $phys"
