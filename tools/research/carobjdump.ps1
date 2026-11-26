# The player's car object over a race (2026-11-26; for the HUD's race position / laps / lap time): boots the test grid
# with the race AI driving the player's car, finds the car object that points at the player's physics object (the
# cars' addresses from the log's "live: car XXXXXXXX" lines), and dumps 16 KB of it -Count times -Every seconds
# apart (<Out>\car.txt: elapsed ms, hex). Look for a float growing with time (lap / race time) and small integers.
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\carobjdump.ps1 -Out <dir>
param([string]$Out, [int]$Count = 40, [double]$Every = 1.0, [int]$Size = 16384)
$ErrorActionPreference = 'Continue'
$r = (Resolve-Path "$PSScriptRoot\..\..\..\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"; $t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'; $env:FM3_AI_PLAYER = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) { Start-Sleep 3; if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break } }
foreach ($v in 'FM3_GRID_TEST', 'FM3_MINIMIZED', 'FM3_LIVE', 'FM3_AI_PLAYER') { Set-Item "Env:$v" '' }
if (-not $frozen) { throw 'no grid' }
. "$r\tools\fm3ctl.ps1"
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
Start-Sleep 3
$text = Get-Content $log -Raw
$phys = ([regex]::Matches($text, 'live: player car physics ([0-9A-F]{8})') | Select-Object -Last 1).Groups[1].Value
$cars = [regex]::Matches($text, 'live: car ([0-9A-F]{8}) at') | % { $_.Groups[1].Value } | Select-Object -Unique
"physics $phys, cars $($cars -join ' ')" | Set-Content "$Out\info.txt"
$player = ''
foreach ($c in $cars) {
    $a = [Convert]::ToUInt32($c, 16)
    for ($k = 0; $k -lt 4 -and -not $player; $k++) {
        $h = (Fm3 ("peek {0:X8} 4096" -f ($a + 4096 * $k))) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
        $i = $h.IndexOf($phys)
        if ($i -ge 0 -and ($i % 8) -eq 0) { $player = $c; "player car $c (physics pointer at +$($k * 4096 + $i / 2))" | Add-Content "$Out\info.txt" }
    }
    if ($player) { break }
}
if (-not $player) { $player = $cars[0]; "no car points at the physics object: dumping $player" | Add-Content "$Out\info.txt" }
$a = [Convert]::ToUInt32($player, 16)
Remove-Item "$Out\car.txt" -ErrorAction SilentlyContinue
$sw = [Diagnostics.Stopwatch]::StartNew()
for ($n = 0; $n -lt $Count; $n++) {
    $hex = ''
    for ($k = 0; $k -lt $Size / 4096; $k++) { $hex += (Fm3 ("peek {0:X8} 4096" -f ($a + 4096 * $k))) -replace '.*"hex":"([0-9A-F]*)".*', '$1' }
    "$($sw.ElapsedMilliseconds) $hex" | Add-Content "$Out\car.txt"
    Start-Sleep $Every
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done $player"
