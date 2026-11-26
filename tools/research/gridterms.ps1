# The paint's terms on the frozen CrownJewel test grid (2026-11-25): boots the grid, edits the game's paint pixel shader
# (e41e183a423e6f1b) live to output one term per mode (0 as is, 1 reflection r7.x x r4, 2 its angle factor r7.x, 3 its
# environment part r4, 4 the lit paint without the reflection oC0 - r7.x x r4), and saves the game's picture per mode.
# Compare with offline renders of out\world\ladera.gltf with FM3_PAINT_DEBUG = the same mode (tools\car_regions.py).
param([string]$Out = "$env:TEMP\gridterms", [string]$Modes = '0,1,2,3')
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"
$t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    Start-Sleep 3
    if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break }
    if (((Get-Date) - $t0).TotalSeconds -gt 15 -and -not (Get-Process fm3 -ErrorAction SilentlyContinue)) { break }
}
Remove-Item Env:FM3_GRID_TEST, Env:FM3_MINIMIZED -ErrorAction SilentlyContinue
if (-not $frozen) { throw "the grid did not freeze (see $log)" }
. "$r\tools\fm3ctl.ps1"
Start-Sleep 3
$expr = @{ '1' = 'float4(r7.x * r4.xyz, 1)'; '2' = 'float4(r7.xxx, 1)'; '3' = 'float4(r4.xyz, 1)';
    '5' = 'float4(abs(input.o[5].www) * 0.368, 1)';  # the reflection's per-vertex weight as the shader uses it
    '6' = 'float4(input.o[1].www, 1)';  # the per-vertex value that scales the angle factor (1 - w)
    '7' = 'float4(TFetch2D(10, float3(input.o[4].x, input.o[4].y, input.o[4].x), false, 0.0, float2(0.0, 0.0)).xxx, 1)';  # track lightmap
    # the static cube (t7) at a face's centre (cube coordinates x, y in 1..2, z = face; exponent adjust applied), and
    # constants that calibrate the picture's response
    '8' = 'float4(TFetch(7, float3(1.5, 1.5, 2.0), false, false, 0.0, float2(0.0, 0.0)).xyz, 1)';
    '9' = 'float4(TFetch(7, float3(1.5, 1.5, 0.0), false, false, 0.0, float2(0.0, 0.0)).xyz, 1)';
    '13' = 'float4(input.o[5].xyz, 1)';  # the vertex shader's ambient (transfer SH . shHemisphericalLightR/G/B)
    '14' = 'float4(input.o[2].www * 0.5, 1)';  # its sun term (transfer SH . shDirectionalLightI), halved
    # the static cube itself, tiled over the paint: 64 px tiles in a 3 x 2 grid of faces 0-5 (cube coordinates s, t in 1..2)
    '20' = 'float4(TFetch(7, float3(1.0 + frac(input.pos.x / 64.0), 1.0 + frac(input.pos.y / 64.0), fmod(floor(input.pos.x / 64.0), 3.0) + 3.0 * fmod(floor(input.pos.y / 64.0), 2.0)), false, false, 0.0, float2(0.0, 0.0)).xyz, 1)';
    '10' = 'float4(0.1, 0.1, 0.1, 1)'; '11' = 'float4(0.25, 0.25, 0.25, 1)'; '12' = 'float4(0.5, 0.5, 0.5, 1)' }
foreach ($m in ($Modes -split ',')) {
    if ($m -eq '0') { Fm3 'ps e41e183a423e6f1b' | Out-Null } else { Fm3 "ps e41e183a423e6f1b $($expr[$m])" | Out-Null }
    Start-Sleep 8
    Fm3 "shot $Out\game$m.png" | Out-Null
    Start-Sleep 1
    "mode $m"
}
Select-String -Path $log -Pattern 'failed to compile' | Select-Object -Last 3 | % { $_.Line }
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
