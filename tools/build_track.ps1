# build_track.ps1: any FM3 track as a Godot scene from the game's files alone, no frame capture (PLAN-CARS.md phase 5).
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\build_track.ps1 -Track AmalfiGP [-Ribbon 01] [-Render]
#
# Unpacks Media\Tracks\<Track>\bin.zip to work\assets\tracks\<track> once (tools\fm3unzip), exports
# frame-ir\out\world\<track>.gltf (+ .bin, _tex; game-derived, git-ignored) with the layout's .pvs (Ribbon_<Ribbon>, the
# first one by default): track models, textures, lightmaps, props, sky, the static car cube; a camera above the middle of
# the track (or -CameraAt 'x,y,z:tx,ty,tz', glTF space). -Render saves out\world\<track>.png from that camera.
# Look around: Godot_v4.7.2-stable_win64.exe --path frame-ir\godot -s res://viewer/world_view.gd -- --gltf <abs gltf> --lit --fly
# (Ladera with the grid capture, cars and the live mirror: rebuild_ladera.ps1.)
param(
    [Parameter(Mandatory = $true)][string]$Track,
    [string]$Ribbon = '',
    [string]$CameraAt = '',
    [string]$Fm3 = '',
    [switch]$Render
)
$ErrorActionPreference = 'Stop'
# (the default here, not in param(): Windows PowerShell 5.1 leaves $PSScriptRoot empty in parameter defaults)
if (-not $Fm3) { $Fm3 = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))) 'FM3-ReGPU recomp' }
$repo = Split-Path -Parent $PSScriptRoot
$godotDir = Split-Path -Parent $repo
$media = Join-Path $Fm3 "reference\rexglue recomp reference\hl360-forza3\game\disc1\Media\Tracks\$Track"
if (-not (Test-Path $media)) { throw "no track folder: $media" }
$name = $Track.ToLower()
$src = Join-Path $godotDir "work\assets\tracks\$name"
if ($name -eq 'crownjewel' -and (Test-Path (Join-Path $godotDir 'work\assets\crownjewel'))) { $src = Join-Path $godotDir 'work\assets\crownjewel' }
if (-not (Test-Path $src)) {
    Write-Host "unpacking $Track\bin.zip"
    & (Join-Path $repo 'tools\fm3unzip\fm3unzip.exe') (Join-Path $media 'bin.zip') $src | Out-Null
}
$pvsList = @(Get-ChildItem $media -Recurse -Filter *.pvs | Sort-Object FullName)
if (-not $pvsList) { throw "no .pvs under $media" }
$pvs = if ($Ribbon) { $pvsList | Where-Object { $_.Directory.Name -eq "Ribbon_$Ribbon" } | Select-Object -First 1 } else { $pvsList[0] }
if (-not $pvs) { throw "no Ribbon_$Ribbon .pvs (have: $(($pvsList | ForEach-Object { $_.Directory.Name }) -join ', '))" }
Write-Host "layout $($pvs.Directory.Name)"
$out = Join-Path $repo "out\world\$name.gltf"
$py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" }
$args_ = @((Join-Path $repo 'tools\fm3_track_export.py'), $src, $out, '--pvs', $pvs.FullName)
if ($CameraAt) { $args_ += @('--camera-at', $CameraAt) }
$ErrorActionPreference = 'Continue'  # (numpy warnings on stderr)
& $py @args_
if ($LASTEXITCODE) { throw 'fm3_track_export.py failed' }
if ($Render) {
    $ErrorActionPreference = 'Continue'  # (Godot's warnings on stderr)
    $godot = Join-Path $godotDir 'Godot_v4.7.2-stable_win64_console.exe'
    & $godot --path (Join-Path $repo 'godot') -s res://viewer/world_view.gd -- --gltf $out --lit --size 1280x720 --out ([IO.Path]::ChangeExtension($out, '.png')) 2>&1 |
        Select-String 'saved'
}
