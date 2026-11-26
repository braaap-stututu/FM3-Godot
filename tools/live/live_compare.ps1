# Live mirror picture check (LIVE.md "Checks"): boots FM3's test grid (minimized, FM3_LIVE on; -AiPlayer: the race AI
# drives the player's car), starts world_view.gd --live beside it, and compares the game's own screenshot with Godot's
# picture (compare.gd, mean |diff| per channel) at frozen moments: the grid, then after each step.
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\live\live_compare.ps1 [-AiPlayer] [-Steps 'race6:6,race15:9']
#       [-Cameras 2]
#
# -Steps name:seconds,...: let the race run that long, freeze (FM3_FREEZE_TIME), compare. -Cameras N: on the grid, press
# RB N times (the next camera view each) and compare each view. Output: frame-ir\out\live\compare\<name>-{game,godot,cmp}.png
# -NoFreeze: take each step's pictures while the race runs (the game's and Godot's then differ by milliseconds; for
# what freezing hides, e.g. the wheels' motion blur, which the viewer takes from the cars' speed).
param([switch]$AiPlayer, [string]$Steps = '', [int]$Cameras = 0, [switch]$NoFreeze, [string]$Gltf = '', [string]$ViewerArgs = '')
$ErrorActionPreference = 'Stop'
# The game at the viewer's anti-aliasing (4x MSAA, 2026-11-26): the user's FSR 3 forces FM3's MSAA to 1x; set
# FM3_UPSCALER / FM3_MSAA / FM3_AA beforehand to compare another setting.
if (-not $env:FM3_UPSCALER) { $env:FM3_UPSCALER = 'off' }
if (-not $env:FM3_MSAA) { $env:FM3_MSAA = '4' }
if (-not $env:FM3_AA) { $env:FM3_AA = 'off' }
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
$out = "$g\frame-ir\out\live\compare"
New-Item -ItemType Directory -Force $out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'
if ($AiPlayer) { $env:FM3_AI_PLAYER = '1' }
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    Start-Sleep 3
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
if (-not $frozen) { throw "the grid did not freeze (see $log; a sleeping monitor makes Vulkan fail at start)" }
. "$r\tools\fm3ctl.ps1"
$godot = "$g\Godot_v4.7.2-stable_win64_console.exe"
$liveOut = "$out\godot.png"
$gltfPath = if ($Gltf) { (Resolve-Path $Gltf).Path } else { "$g\frame-ir\out\world\ladera.gltf" }  # -Gltf: another scene (a capture-free track: its cars come from the car library)
$glog = "$out\godot.log"
$vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf',
    "`"$gltfPath`"", '--lit', '--live', '7342', '--size', '1280x720', '--out', "`"$liveOut`"") + @($ViewerArgs -split ' ' | Where-Object { $_ })
$p = Start-Process $godot -ArgumentList $vargs `
    -RedirectStandardOutput $glog -RedirectStandardError "$out\godot.err.log" -PassThru -WindowStyle Normal
for ($i = 0; $i -lt 90 -and -not (Select-String -Path $glog -Pattern 'meshes attached' -Quiet -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
Start-Sleep 2
function Compare-View([string]$name) {
    Remove-Item $liveOut -ErrorAction SilentlyContinue
    New-Item -ItemType File "$liveOut.shot" -Force | Out-Null
    for ($i = 0; $i -lt 20 -and -not (Test-Path $liveOut); $i++) { Start-Sleep -Milliseconds 250 }
    Copy-Item $liveOut "$out\$name-godot.png" -Force
    Save-Fm3Shot "live-$name.png" | Out-Null
    Copy-Item "$r\out\shots\live-$name.png" "$out\$name-game.png" -Force
    $res = & $godot --path "$g\frame-ir\godot" -s res://viewer/compare.gd -- "$out\$name-game.png" "$out\$name-godot.png" "$out\$name-cmp.png" 1280 2>&1 |
        Select-String 'mean'
    "$name : $($res.Line)"
}
try {
    Compare-View 'grid'
    for ($k = 1; $k -le $Cameras; $k++) {
        Fm3 'press RB 500' | Out-Null
        Start-Sleep 3
        Compare-View "cam$($k + 1)"
    }
    foreach ($s in ($Steps -split ',' | Where-Object { $_ })) {
        $name, $sec = $s -split ':'
        Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
        Start-Sleep ([int]$sec)
        if ($NoFreeze) {
            Compare-View $name
        } else {
            Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
            Start-Sleep 2
            Compare-View $name
        }
    }
    Select-String -Path $glog -Pattern 'live (car|director)' | ForEach-Object { $_.Line }
} finally {
    Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
    Get-Process fm3 -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
}
