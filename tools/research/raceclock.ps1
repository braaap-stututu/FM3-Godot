# The race clock / laps / position hunt (2026-11-27): boots the test grid with the race AI driving the player, lets the
# race run, freezes at -T1 and -T2 seconds, and each time lists every guest float near the elapsed time (the debug
# server's findf, added to FM3-ReGPU's ReGPU debug.cpp that day) and takes a shot (the HUD shows the race time, lap and
# place). Then it dumps 4 KB around each address found both times (<Out>\clock.txt). Read the HUD from the shots.
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\raceclock.ps1 -Out <dir> [-T1 20] [-T2 45]
param([string]$Out, [double]$T1 = 20, [double]$T2 = 45, [double]$T3 = 75)
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
$sw = [Diagnostics.Stopwatch]::StartNew()
$sets = @()
$k = 0
foreach ($t in @($T1, $T2, $T3)) {
    while ($sw.Elapsed.TotalSeconds -lt $t) { Start-Sleep -Milliseconds 100 }
    Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
    $w = $sw.Elapsed.TotalSeconds
    Start-Sleep 1
    Fm3 "shot $Out\clock$k.png" | Out-Null
    $res = Fm3 ("findf {0} {1} 300000" -f ($w - 3), ($w + 0.5))
    "$k wall $w $res" | Add-Content "$Out\findf.txt"
    $sets += , ([regex]::Matches($res, '\["([0-9A-F]{8})",(-?[0-9.]+)\]') | % { @{ a = $_.Groups[1].Value; v = [double]$_.Groups[2].Value } })
    $k++
    $sw.Stop(); Start-Sleep 1
    Fm3 'env FM3_FREEZE_TIME 0' | Out-Null
    $sw.Start()
}
# addresses in all three lists, rising
$m0 = @{}; foreach ($h in $sets[0]) { $m0[$h.a] = $h.v }
$m1 = @{}; foreach ($h in $sets[1]) { $m1[$h.a] = $h.v }
$both = @()
foreach ($h in $sets[2]) { if ($m0.ContainsKey($h.a) -and $m1.ContainsKey($h.a) -and $h.v -gt $m1[$h.a] -and $m1[$h.a] -gt $m0[$h.a]) { $both += "$($h.a) $($m0[$h.a]) $($m1[$h.a]) $($h.v)" } }
$both | Set-Content "$Out\clock.txt"
"rising in all three: $($both.Count)" | Add-Content "$Out\findf.txt"
Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
Fm3 "shot $Out\clock_end.png" | Out-Null
foreach ($line in ($both | Select-Object -First 12)) {
    $a = [Convert]::ToUInt32(($line -split ' ')[0], 16)
    $base = ($a - 2048) -band 0xFFFFFFFC
    $h = (Fm3 ("peek {0:X8} 4096" -f $base)) -replace '.*"hex":"([0-9A-F]*)".*', '$1'
    "{0:X8} $h" -f $base | Add-Content "$Out\around.txt"
}
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
"done: $($both.Count) rising"
