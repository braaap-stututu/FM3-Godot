# Live mirror picture check on any Free Play environment (2026-11-24): boots FM3 (minimized, FM3_LIVE on) through the
# recomp's tour route (tools\tour.ps1: Free Play > Quick Race > Acura RSX Type-S > environment), starts the first layout,
# freezes the world during the countdown, starts world_view.gd --live on the track's capture-free scene beside it and
# compares the game's own picture with Godot's (compare.gd), as live_compare.ps1 does on the CrownJewel career grid.
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\live\live_track.ps1 -Index 3 -Gltf <abs>\out\world\catalunya.gltf
#       [-Name catalunya] [-FreezeAfter 8] [-ViewerArgs '...']
#
# -Index: the environment (tour.ps1's list: 0 Amalfi Coast, 3 Catalunya, 7 Le Mans, ... 24 Twin Ring Motegi).
# Output: frame-ir\out\live\tracks\<Name>-{game,godot,cmp}.png and the compare line.
param([Parameter(Mandatory = $true)][int]$Index, [Parameter(Mandatory = $true)][string]$Gltf, [string]$Name = '',
    [double]$FreezeAfter = 8.0, [string]$ViewerArgs = '', [int]$Cameras = 0)
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
if (-not $Name) { $Name = [IO.Path]::GetFileNameWithoutExtension($Gltf) }
$out = "$g\frame-ir\out\live\tracks"
New-Item -ItemType Directory -Force $out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
# (the tour's state checks run `python`: this session's PATH may lack it)
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "live-$Name"
Pop-Location
if (-not (Start-TourBoot @{ FM3_LIVE = '1' })) { Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }; throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2                                 # Go race: loading, then the pre-race menu over the fly-over
Start-Sleep 50
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A $FreezeAfter                      # Start race; the car intro and countdown
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null          # the world stops (frame_time.cpp)
Start-Sleep 2
for ($k = 0; $k -lt $Cameras; $k++) { Fm3 'press RB 500' | Out-Null; Start-Sleep 2 }
# the viewer beside it
$godot = "$g\Godot_v4.7.2-stable_win64_console.exe"
$liveOut = "$out\$Name-godot-raw.png"
Remove-Item $liveOut, "$liveOut.shot" -ErrorAction SilentlyContinue
$vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf', "`"$Gltf`"", '--lit',
    '--live', '7342', '--size', '1280x720', '--out', "`"$liveOut`"") + @($ViewerArgs -split ' ' | Where-Object { $_ })
$p = Start-Process $godot -ArgumentList $vargs -RedirectStandardOutput "$out\$Name-godot.log" `
    -RedirectStandardError "$out\$Name-godot.err.log" -PassThru -WindowStyle Normal
Start-Sleep 25
$gameShot = "$out\$Name-game.png"
Remove-Item $gameShot -ErrorAction SilentlyContinue
Fm3 "shot $gameShot" | Out-Null
New-Item -ItemType File "$liveOut.shot" | Out-Null
for ($i = 0; $i -lt 60 -and -not (Test-Path $liveOut); $i++) { Start-Sleep 1 }
Start-Sleep 1
if (Test-Path $liveOut) { Copy-Item $liveOut "$out\$Name-godot.png" -Force }
$res = & $godot --headless --path "$g\frame-ir\godot" -s res://viewer/compare.gd -- $gameShot "$out\$Name-godot.png" "$out\$Name-cmp.png" 1280 2>&1 |
    Select-String 'mean'
"$Name : $($res.Line)"
Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
