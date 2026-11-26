# The game's exposure on any Free Play track (2026-11-26): boots FM3 to environment -Index (tour.ps1's list), freezes in
# the countdown, then edits the final pass (ps 5b7efac9b0c87a00) live to output its vertex interpolants, with the display
# gamma off (REGPU_NO_GAMMA), and saves a shot per mode. input.o[1].y = 0.1 / W (the exposure's white point), so W =
# 0.4 / (pixel / 255) in mode 1. Compare with the viewer's own W (world_view.gd logs "exposure: L .. k .. W ..").
param([int]$Index = 17, [string]$Name = 'sebring', [string]$Out = "$env:TEMP\wtrack", [double]$FreezeAfter = 11.0, [string]$Modes = '1,2,3,4,5,6,7')
$ErrorActionPreference = 'Continue'
$g = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$r = (Resolve-Path "$g\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
foreach ($kv in @{ FM3_UPSCALER = 'off'; FM3_MSAA = '4'; FM3_AA = 'off' }.GetEnumerator()) {
    if (-not [Environment]::GetEnvironmentVariable($kv.Key)) { [Environment]::SetEnvironmentVariable($kv.Key, $kv.Value) }
}
Push-Location $r
. "$r\tools\tour.ps1" -Run "w-$Name"
Pop-Location
if (-not (Start-TourBoot @{ })) { throw 'boot route failed' }
for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
Tour-Press A 2
Start-Sleep 70
if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
Tour-Press A $FreezeAfter
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Start-Sleep 4
Fm3 "shot $Out\$Name-game.png" | Out-Null
Fm3 'switch REGPU_NO_GAMMA 1' | Out-Null
Start-Sleep 2
Fm3 "shot $Out\$Name-w0.png" | Out-Null
Start-Sleep 1
$expr = [ordered]@{ '1' = 'float4(input.o[1].yyy * 4.0, 1)'; '2' = 'float4(input.o[1].xzw, 1)'; '3' = 'float4(input.o[2].xyz, 1)';
    '4' = 'float4(input.o[3].xyz, 1)'; '5' = 'float4(0.5, 0.5, 0.5, 1)';
    # the scene (t0, x 0.25: its range above 1) and the bloom (t4) alone
    '6' = 'float4(TFetch2D(0, float3(input.o[0].x, input.o[0].y, input.o[0].x), false, 0.0, float2(0.0, 0.0)).xyz * 0.25, 1)';
    '7' = 'float4(TFetch2D(4, float3(input.o[0].x, input.o[0].y, input.o[0].x), false, 0.0, float2(0.0, 0.0)).xyz, 1)' }
foreach ($m in ($Modes -split ',')) {
    Fm3 "ps 5b7efac9b0c87a00 $($expr[$m])" | Out-Null
    Start-Sleep 6
    Fm3 "shot $Out\$Name-w$m.png" | Out-Null
    Start-Sleep 1
    "mode $m"
}
Fm3 'ps 5b7efac9b0c87a00' | Out-Null
Fm3 'switch REGPU_NO_GAMMA 0' | Out-Null
Select-String -Path "$r\out\run\fm3.log" -Pattern 'failed to compile' | Select-Object -Last 3 | % { $_.Line }
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
