# The player's car-physics object over time (2026-11-26): boots the test grid with the race AI driving the player's
# car, lets it race, and dumps the physics object (8 KB) -Count times -Every seconds apart (<Out>\phys.txt, one line
# per dump: elapsed ms, hex). For finding fields by their behaviour (slip ratio against the wheel / car speeds, ...).
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\physdump.ps1 -Out <dir> [-Count 40] [-Every 0.5]
param([string]$Out, [int]$Count = 40, [double]$Every = 0.5, [double]$Start = 6)
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
Start-Sleep $Start
$phys = ([regex]::Matches((Get-Content $log -Raw), 'live: player car physics ([0-9A-F]{8})') | Select-Object -Last 1).Groups[1].Value
$a = [Convert]::ToUInt32($phys, 16)
Remove-Item "$Out\phys.txt" -ErrorAction SilentlyContinue
$sw = [Diagnostics.Stopwatch]::StartNew()
for ($k = 0; $k -lt $Count; $k++) {
    $h0 = (Fm3 ("peek {0:X8} 4096" -f $a)) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    $h1 = (Fm3 ("peek {0:X8} 4096" -f ($a + 4096))) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    "$($sw.ElapsedMilliseconds) $h0$h1" | Add-Content "$Out\phys.txt"
    Start-Sleep $Every
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done $phys"
