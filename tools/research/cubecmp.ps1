# The game's car reflection cube against the viewer's live cube (2026-11-25): boots FM3 to Free Play environment N
# (REGPU_NO_PACKED_CONSTANTS=1), freezes in the countdown, starts the live viewer with FM3_DUMP_LIVE_CUBE=1 (its six
# faces beside its picture), then takes a debug-server capture (every draw with its constants, resolved images into
# the recomp's out/run/out/res). Output in -Out: game.png, godot.png (+ .cube<k>.png), cap.log.
param([int]$Index = 24, [string]$Gltf = '', [string]$Out = "$env:TEMP\cubecmp")
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "cubecmp"
Pop-Location
if (-not (Start-TourBoot @{ FM3_LIVE = '1'; REGPU_NO_PACKED_CONSTANTS = '1' })) { throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2
Start-Sleep 70
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A 11
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Start-Sleep 2
$godot = "$g\Godot_v4.7.2-stable_win64_console.exe"
$liveOut = "$Out\godot.png"
Remove-Item "$Out\*" -ErrorAction SilentlyContinue
$env:FM3_DUMP_LIVE_CUBE = '1'
$vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf', "`"$Gltf`"", '--lit',
    '--live', '7342', '--size', '1280x720', '--out', "`"$liveOut`"")
$p = Start-Process $godot -ArgumentList $vargs -RedirectStandardOutput "$Out\godot.log" -RedirectStandardError "$Out\godot.err.log" -PassThru
Remove-Item Env:FM3_DUMP_LIVE_CUBE
Start-Sleep 25
Fm3 "shot $Out\game.png" | Out-Null
New-Item -ItemType File "$liveOut.shot" | Out-Null
for ($i = 0; $i -lt 60 -and -not (Test-Path $liveOut); $i++) { Start-Sleep 1 }
Start-Sleep 2
Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
$log = "$r\out\run\fm3.log"
$before = (Get-Content $log).Count
Fm3 'capture' | Out-Null
Fm3 'wait 3' | Out-Null
Start-Sleep 8
@(Get-Content $log | Select-Object -Skip $before) | Set-Content "$Out\cap.log"
"captured; out in $Out"
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
