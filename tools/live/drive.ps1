# Drive the test race yourself, seen only through Godot (LIVE.md "Driving it"): FM3 boots to the test grid (the
# CrownJewel career race, Ladera short reverse) with the live stream, a 60 fps cap and keyboard/wheel input read even
# while the Godot window is in front; once the grid freezes, ReGPU's drawing is switched off (REGPU_NO_RENDER: the
# game runs, nothing is drawn), the Godot viewer starts (60 fps cap), attaches the cars, and the countdown runs. Close
# the viewer (Esc) and the game is closed too (it saves on exit).
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\live\drive.ps1 [-Fps 60] [-KeepGameRendering]
#       [-AiPlayer] [-Seconds N] [-Log csv]
#
# -AiPlayer (the race AI drives your car) and -Seconds N (stop after N s of racing) are for unattended tests; -Log writes
# the viewer's --live-log. The game must be closed first; the monitor awake.
param([int]$Fps = 60, [switch]$KeepGameRendering, [switch]$AiPlayer, [int]$Seconds = 0, [string]$Log = '')
$ErrorActionPreference = 'Stop'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'FM3 is already running: close it first' }
$out = "$g\frame-ir\out\live"
New-Item -ItemType Directory -Force $out | Out-Null
$fm3log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_LIVE = '1'; $env:FM3_MAX_FPS = "$Fps"; $env:FM3_INPUT_BACKGROUND = '1'
$env:FM3_MINIMIZED = if ($KeepGameRendering) { '0' } else { '1' }
if ($AiPlayer) { $env:FM3_AI_PLAYER = '1' }
Write-Host "drive: starting FM3 (test grid, $Fps fps cap, live stream on)..."
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 240) {
    Start-Sleep 2
    if ((Test-Path $fm3log) -and (Get-Item $fm3log).LastWriteTime -gt $t0 -and ((Get-Content $fm3log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
if (-not $frozen) {
    Get-Process fm3 -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    throw "FM3 did not reach the grid (see $fm3log; a sleeping monitor makes Vulkan fail at start)"
}
. "$r\tools\fm3ctl.ps1"
if (-not $KeepGameRendering) {
    Fm3 'switch REGPU_NO_RENDER 1' | Out-Null
    Write-Host 'drive: on the grid; the game''s own rendering is off (REGPU_NO_RENDER)'
}
$glog = "$out\drive-godot.log"
$vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf',
    "`"$g\frame-ir\out\world\ladera.gltf`"", '--lit', '--live', '7342', '--fps', "$Fps", '--size', '1920x1080')
if ($Log) { $vargs += @('--live-log', "`"$Log`"") }
$p = Start-Process "$g\Godot_v4.7.2-stable_win64_console.exe" -ArgumentList $vargs -RedirectStandardOutput $glog -PassThru -WindowStyle Normal
for ($i = 0; $i -lt 120 -and -not (Select-String -Path $glog -Pattern 'meshes attached' -Quiet -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
Select-String -Path $glog -Pattern 'meshes attached' | ForEach-Object { '  ' + ($_.Line -replace '^world_view: ', '') }
try { (New-Object -ComObject WScript.Shell).AppActivate($p.Id) | Out-Null } catch {}
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
Write-Host 'drive: GO - the countdown is running. Drive with your wheel, pad or keyboard; the Godot window shows the race.'
Write-Host '       Esc in the Godot window ends it (FM3 is closed then too).'
$raceStart = Get-Date
try {
    while (-not $p.HasExited) {
        Start-Sleep 1
        if ($Seconds -gt 0 -and ((Get-Date) - $raceStart).TotalSeconds -ge $Seconds) { break }
        if (-not (Get-Process fm3 -ErrorAction SilentlyContinue)) { Write-Host 'drive: FM3 has closed'; break }
    }
    if ($Seconds -gt 0) {
        "game status: $(Fm3 'status')"
        Select-String -Path $glog -Pattern 'viewer \d+ fps' | Select-Object -Last 2 | ForEach-Object { '  ' + ($_.Line -replace '.*\(', '(') }
    }
} finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -ErrorAction SilentlyContinue }
    Get-Process fm3 -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Write-Host 'drive: done (FM3 closed and saved; viewer log in frame-ir\out\live\drive-godot.log)'
}
