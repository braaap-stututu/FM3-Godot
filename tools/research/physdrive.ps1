# The player's car-physics object under driving that makes the tyres slip (2026-11-26): boots the CrownJewel test grid
# (no race AI driving the player), then drives with the debug server's virtual pad: full throttle from the start
# (wheelspin), hard braking, throttle with full steering lock (cornering slip); dumps the physics object (8 KB) every
# -Every seconds throughout (<Out>\phys.txt: elapsed ms, phase, hex). For finding slip ratio / slip angle fields.
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\physdrive.ps1 -Out <dir>
param([string]$Out, [double]$Every = 0.12)
$ErrorActionPreference = 'Continue'
$r = (Resolve-Path "$PSScriptRoot\..\..\..\..\FM3-ReGPU recomp").Path
New-Item -ItemType Directory -Force $Out | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"; $t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'; $env:FM3_LIVE = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
$frozen = $false
while (((Get-Date) - $t0).TotalSeconds -lt 180) { Start-Sleep 3; if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { $frozen = $true; break } }
foreach ($v in 'FM3_GRID_TEST', 'FM3_MINIMIZED', 'FM3_LIVE') { Set-Item "Env:$v" '' }
if (-not $frozen) { throw 'no grid' }
. "$r\tools\fm3ctl.ps1"
Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
Start-Sleep 6   # (the countdown)
$phys = ([regex]::Matches((Get-Content $log -Raw), 'live: player car physics ([0-9A-F]{8})') | Select-Object -Last 1).Groups[1].Value
$a = [Convert]::ToUInt32($phys, 16)
Remove-Item "$Out\phys.txt" -ErrorAction SilentlyContinue
$sw = [Diagnostics.Stopwatch]::StartNew()
function Dump($phase) {
    $h0 = (Fm3 ("peek {0:X8} 4096" -f $a)) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    $h1 = (Fm3 ("peek {0:X8} 4096" -f ($a + 4096))) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    "$($sw.ElapsedMilliseconds) $phase $h0$h1" | Add-Content "$Out\phys.txt"
}
$phases = @(@('launch', 6.0, { Fm3 'trigger R 1.0' | Out-Null }),
            @('brake', 2.5, { Fm3 'trigger R 0' | Out-Null; Fm3 'trigger L 1.0' | Out-Null }),
            @('accel', 4.0, { Fm3 'trigger L 0' | Out-Null; Fm3 'trigger R 1.0' | Out-Null }),
            @('steer', 4.0, { Fm3 'trigger R 0.6' | Out-Null; Fm3 'stick L 1 0 4000' | Out-Null }),
            @('steerleft', 4.0, { Fm3 'stick L -1 0 4000' | Out-Null }))
foreach ($p in $phases) {
    & $p[2]
    $end = $sw.Elapsed.TotalSeconds + $p[1]
    while ($sw.Elapsed.TotalSeconds -lt $end) { Dump $p[0]; Start-Sleep $Every }
}
Fm3 'release all' | Out-Null
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done $phys"
