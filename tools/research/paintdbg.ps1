# The paint's terms one by one, game against viewer (2026-11-25): boots FM3 to Free Play environment N, freezes in the
# countdown; for each mode the game's paint ps (e41e183a423e6f1b) is edited live to output one term (1 reflection
# r7.x x r4, 2 its angle factor r7.x, 3 its environment part r4; 0 = as is) and the viewer runs with FM3_PAINT_DEBUG
# = the same mode (fm3_carpaint.gdshader debug_out). Output in -Out: game<m>.png, godot<m>.png.
param([int]$Index = 24, [string]$Gltf = '', [string]$Out = "$env:TEMP\paintdbg", [string]$Modes = '0,1,2,3')
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
Remove-Item "$Out\*" -ErrorAction SilentlyContinue
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "paintdbg"
Pop-Location
if (-not (Start-TourBoot @{ FM3_LIVE = '1' })) { throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2
Start-Sleep 70
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A 11
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Start-Sleep 2
$godot = "$g\Godot_v4.7.2-stable_win64_console.exe"
$expr = @{ '1' = 'float4(r7.x * r4.xyz, 1)'; '2' = 'float4(r7.xxx, 1)'; '3' = 'float4(r4.xyz, 1)' }
foreach ($m in ($Modes -split ',')) {
    if ($m -eq '0') { Fm3 'ps e41e183a423e6f1b' | Out-Null } else { Fm3 "ps e41e183a423e6f1b $($expr[$m])" | Out-Null }
    Start-Sleep 8
    Fm3 "shot $Out\game$m.png" | Out-Null
    $liveOut = "$Out\godot$m.png"
    $env:FM3_PAINT_DEBUG = $m
    $vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf', "`"$Gltf`"", '--lit',
        '--live', '7342', '--size', '1280x720', '--out', "`"$liveOut`"")
    $p = Start-Process $godot -ArgumentList $vargs -RedirectStandardOutput "$Out\godot$m.log" -RedirectStandardError "$Out\godot$m.err.log" -PassThru
    Remove-Item Env:FM3_PAINT_DEBUG
    Start-Sleep 25
    New-Item -ItemType File "$liveOut.shot" | Out-Null
    for ($i = 0; $i -lt 60 -and -not (Test-Path $liveOut); $i++) { Start-Sleep 1 }
    Start-Sleep 2
    Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
    Start-Sleep 3
    "mode $m done"
}
Select-String -Path "$r\out\run\fm3.log" -Pattern 'failed to compile' | Select-Object -Last 3 | % { $_.Line }
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
