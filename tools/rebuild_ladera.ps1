# rebuild_ladera.ps1: the whole Ladera (CrownJewel) scene for the Godot viewer, from the game's files plus the grid capture.
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\rebuild_ladera.ps1 [-Fm3 <FM3-ReGPU recomp folder>] [-Compare]
#
# Inputs (paths relative to the Godot folder = this repo's parent; see HANDOFF.md):
#   work\fir\grid-single-1f.fir         the captured grid frame (ReGPU fir_tap); grid-single-1f.png its screenshot
#   work\assets\crownjewel              Media\Tracks\CrownJewel\bin.zip extracted (tools\fm3unzip\fm3unzip.exe)
#   work\assets\carbins, work\assets\wheels   Media\Cars\*.zip .carbin files extracted
#   <Fm3>\reference\rexglue recomp reference\hl360-forza3\game\disc1\Media\Tracks\CrownJewel\Ribbon_04\crownjewel_04.pvs
# Outputs (git-ignored, game-derived): frame-ir\out\world\grid.gltf (+ grid_tex), out\world\capmap,
#   out\world\ladera.gltf (+ ladera.bin, ladera_tex) for fly-track.cmd; with -Compare also ladera.png and cmp.png.
param(
    [string]$Fm3 = (Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))) 'FM3-ReGPU recomp'),
    [switch]$Compare
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot           # frame-ir
$godotDir = Split-Path -Parent $repo               # the Godot folder
$work = Join-Path $godotDir 'work'
$godot = Join-Path $godotDir 'Godot_v4.7.2-stable_win64.exe'
$fir = Join-Path $work 'fir\grid-single-1f.fir'
$pvs = Join-Path $Fm3 'reference\rexglue recomp reference\hl360-forza3\game\disc1\Media\Tracks\CrownJewel\Ribbon_04\crownjewel_04.pvs'
$track = Join-Path $work 'assets\crownjewel'
$carbins = Join-Path $work 'assets\carbins'
$wheels = Join-Path $work 'assets\wheels'
foreach ($p in $fir, $pvs, $track, $carbins, $godot) { if (-not (Test-Path $p)) { throw "missing: $p" } }
Set-Location $repo
New-Item -ItemType Directory -Force out\world | Out-Null

Write-Host '1/4 capture -> grid.gltf + material map (fir_world.py)'
$env:FM3_ASSETS = "$carbins;$wheels"            # car material names from the .carbin files (paint, glass, trim)
$capmap = Join-Path $work 'capmap'
if (Test-Path $capmap) { Remove-Item -Recurse -Force $capmap }
python tools\fir_world.py $fir --gltf out\world\grid.gltf --material-map $capmap
if ($LASTEXITCODE) { throw 'fir_world.py failed' }

Write-Host '2/4 material map -> out\world\capmap\track_materials.json (fm3_track_texmap.py)'
if (Test-Path out\world\capmap) { Remove-Item -Recurse -Force out\world\capmap }
Copy-Item -Recurse $capmap out\world\capmap
Push-Location tools
python fm3_track_texmap.py $track ..\out\world\capmap ..\out\world\capmap\track_materials.json
$rc = $LASTEXITCODE
Pop-Location
if ($rc) { throw 'fm3_track_texmap.py failed' }

Write-Host '3/4 track + props + sky + cars -> out\world\ladera.gltf (fm3_track_export.py)'
# (work\fir\grid-cars.json: the game's car matrices on the grid, tools\live_listen.py --save-cars; places every car,
# also the far ones, from its carbin. Without it the cars that fit their captured draws are rebuilt, the rest captured.)
$carMats = Join-Path $work 'fir\grid-cars.json'
$carArgs = if (Test-Path $carMats) { @('--car-matrices', $carMats) } else { @() }
python tools\fm3_track_export.py $track out\world\ladera.gltf --camera-from out\world\grid.gltf `
    --dynamic-from out\world\grid.gltf --carbins $carbins --texmap out\world\capmap --pvs $pvs @carArgs
if ($LASTEXITCODE) { throw 'fm3_track_export.py failed' }

if ($Compare) {
    Write-Host '4/4 render the grid view and compare with the game screenshot'
    $outDir = (Resolve-Path out\world).Path
    & $godot --path godot -s res://viewer/world_view.gd -- --gltf "$outDir\ladera.gltf" --out "$outDir\ladera.png" --size 2560x1440 --lit | Out-Null
    & $godot --headless --path godot -s res://viewer/compare.gd -- (Join-Path $work 'fir\grid-single-1f.png') "$outDir\ladera.png" "$outDir\cmp.png" 1600
} else {
    Write-Host '4/4 skipped (-Compare renders out\world\ladera.png and cmp.png against the game screenshot)'
}
Write-Host 'done: fly-track.cmd opens out\world\ladera.gltf'
