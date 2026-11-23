# Live mirror smoothness test (LIVE.md "Smoothness"): boots FM3's test grid with the race AI driving the player's car
# too (FM3_GRID_TEST + FM3_AI_PLAYER, minimized, FM3_LIVE on), starts world_view.gd --live beside it (logging what it
# shows), lets the race run, then closes both. Analyse with tools\live_smoothness.py [--window 10] <csv>.
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\live\live_smooth.ps1 [-Seconds 60] [-Tag name]
#       [-ViewerArgs '--live-raw'] [-GameEnv 'FM3_X=1;FM3_Y=2'] [-NoGodot]
#
# -NoGodot records the stream itself instead (tools\live_record.py: packet timing, camera/car pairing).
# Output: frame-ir\out\live\smooth\<Tag>.csv and godot-<Tag>.log. The game must be closed first; the monitor awake.
param([switch]$NoGodot, [string]$GameEnv = '', [string]$ViewerArgs = '', [string]$Tag = 'interp', [int]$Seconds = 16)
$ErrorActionPreference = 'Stop'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path          # the Godot folder
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path         # the FM3 repo beside it
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py -or $py -like '*WindowsApps*') { $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" }
$out = "$g\frame-ir\out\live\smooth"
New-Item -ItemType Directory -Force $out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'; $env:FM3_AI_PLAYER = '1'
foreach ($kv in ($GameEnv -split ';' | Where-Object { $_ })) { $k, $v = $kv -split '=', 2; Set-Item "env:$k" $v; "game env $k=$v" }
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    Start-Sleep 3
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
if (-not $frozen) { throw "the grid did not freeze (see $log; a sleeping monitor makes Vulkan fail at start)" }
. "$r\tools\fm3ctl.ps1"
$p = $null
if (-not $NoGodot) {
    $glog = "$out\godot-$Tag.log"
    $vargs = @('--path', "`"$g\frame-ir\godot`"", '-s', 'res://viewer/world_view.gd', '--', '--gltf',
        "`"$g\frame-ir\out\world\ladera.gltf`"", '--lit', '--live', '7342', '--size', '1280x720', '--live-log', "`"$out\$Tag.csv`"") +
        @($ViewerArgs -split ' ' | Where-Object { $_ })
    $p = Start-Process "$g\Godot_v4.7.2-stable_win64_console.exe" -ArgumentList $vargs -RedirectStandardOutput $glog -PassThru -WindowStyle Normal
    for ($i = 0; $i -lt 90 -and -not (Select-String -Path $glog -Pattern 'meshes attached' -Quiet -ErrorAction SilentlyContinue); $i++) { Start-Sleep 1 }
}
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
Start-Sleep 4
if ($NoGodot) {
    & $py "$g\frame-ir\tools\live_record.py" --seconds ([Math]::Max(1, $Seconds - 4))
} else {
    Start-Sleep ([Math]::Max(1, $Seconds - 4))
    Select-String -Path $glog -Pattern 'viewer \d+ fps' | Select-Object -Last 3 | ForEach-Object { $_.Line -replace '.*\(', '(' }
}
"game status: $(Fm3 'status')"
if ($p) { Stop-Process -Id $p.Id -ErrorAction SilentlyContinue }
Get-Process fm3 -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
Start-Sleep 6
if (-not $NoGodot) { & $py "$g\frame-ir\tools\live_smoothness.py" --window 10 "$out\$Tag.csv" }
