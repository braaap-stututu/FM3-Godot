param([string]$Only = '', [switch]$NoBuild)
$sp = "$env:TEMP\claude\b4f71e9586294878\44eb78d4-f1a3-4b9f-ab51-d1a43a9081b2\scratchpad"
Set-Location 'C:\claude code projects\handoff-2026-11-22\Godot\frame-ir'
$map = [ordered]@{ AmalfiGP = 0; Catalunya = 3; LeMans = 7; MapleValley = 8; LagunaSeca = 9; Mugello = 10; NewYork = 11; RoadAmerica = 15;
    RoadAtlanta = 16; Sebring = 17; Silverstone = 20; SunsetInfield = 21; Suzuka = 22; Tsukuba = 23; Motegi = 24 }
foreach ($t in $map.Keys) {
    if ($Only -and ($Only -split ',') -notcontains $t) { continue }
    if (-not $NoBuild) { powershell -ExecutionPolicy Bypass -File tools\build_track.ps1 -Track $t 2>&1 | Out-Null }
    $gl = "$PWD\out\world\$($t.ToLower()).gltf"
    $r = powershell -ExecutionPolicy Bypass -File tools\live\live_track.ps1 -Index $map[$t] -FreezeAfter 11 -Gltf $gl 2>&1 | Select-Object -Last 1
    "$t : $r" | Tee-Object -Append "$sp\survey.log"
    Start-Sleep 5
}
