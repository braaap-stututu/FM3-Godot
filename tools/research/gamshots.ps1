param([int]$Index = 8, [string]$Name = 'maplevalley')
$ErrorActionPreference = 'Continue'
$r = 'C:\claude code projects\handoff-2026-11-22\FM3-ReGPU recomp'
$sp = "$env:TEMP\claude\b4f71e9586294878\44eb78d4-f1a3-4b9f-ab51-d1a43a9081b2\scratchpad"
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "cap-$Name"
Pop-Location
if (-not (Start-TourBoot @{ })) { throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2
Start-Sleep 70
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A 11
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Start-Sleep 3
Fm3 "shot $sp\gam-on.png" | Out-Null
Fm3 'switch REGPU_NO_GAMMA 1' | Out-Null; Start-Sleep 3
Fm3 "shot $sp\gam-off.png" | Out-Null
Fm3 'switch REGPU_NO_GAMMA 0' | Out-Null; Fm3 'switch REGPU_NO_GAMMA_PWL 1' | Out-Null; Start-Sleep 3
Fm3 "shot $sp\gam-table.png" | Out-Null
Fm3 'switch REGPU_NO_GAMMA_PWL 0' | Out-Null
'shots done'
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
