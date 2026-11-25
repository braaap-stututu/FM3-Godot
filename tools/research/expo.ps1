param([int]$Index = 8, [string]$Name = 'maplevalley')
$ErrorActionPreference = 'Continue'
$r = 'C:\claude code projects\handoff-2026-11-22\FM3-ReGPU recomp'
$sp = "$env:TEMP\claude\b4f71e9586294878\44eb78d4-f1a3-4b9f-ab51-d1a43a9081b2\scratchpad"
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "cap-$Name"
Pop-Location
if (-not (Start-TourBoot @{ REGPU_NO_PACKED_CONSTANTS = '1'; REGPU_TRACE_VC = '1' })) { throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2
Start-Sleep 70
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A 11
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Start-Sleep 3
Fm3 "shot $sp\cap-$Name.png" | Out-Null
foreach ($h in '2a342f670b5bb28a', '5b7efac9b0c87a00', '58dc46c8b0b963ea', 'f1a9eb4ba8138c24', '856d0fc8eb697b8e', '4a17014edfabf5f0') {
    Fm3 "hlsl $h out/hlsl/post_$h.hlsl" | Out-Null; Start-Sleep 1
}
$log = "$r\out\run\fm3.log"
$before = (Get-Content $log).Count
Fm3 'capture' | Out-Null
Fm3 'wait 3' | Out-Null
Start-Sleep 5
$lines = @(Get-Content $log | Select-Object -Skip $before)
$lines | Set-Content "$sp\cap-$Name.log"
"captured $($lines.Count) lines"
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
