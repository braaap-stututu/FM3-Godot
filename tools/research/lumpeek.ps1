param([int]$Index = 8, [string]$Name = 'maplevalley', [switch]$Grid)
$ErrorActionPreference = 'Continue'
$r = 'C:\claude code projects\handoff-2026-11-22\FM3-ReGPU recomp'
$sp = "$env:TEMP\claude\b4f71e9586294878\44eb78d4-f1a3-4b9f-ab51-d1a43a9081b2\scratchpad"
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$env:Path = "$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
Push-Location $r
. "$r\tools\tour.ps1" -Run "lum-$Name"
Pop-Location
if ($Grid) {
    # the CrownJewel career test grid (FM3_GRID_TEST: frozen on its own ~23 s after launch)
    $env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'
    Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
    Start-Sleep 60
    $env:FM3_GRID_TEST = ''
} else {
    if (-not (Start-TourBoot @{ })) { throw 'boot route failed' }
    for ($i = 0; $i -lt $Index; $i++) { Tour-Press RIGHT 0.9 }
    if (-not (Tour-Expect trackselect { Tour-Press A 4 } 2 "$Index-trackselect")) { throw 'track select not reached' }
    Tour-Press A 2
    Start-Sleep 70
    if (-not (Tour-Expect menu { Tour-Press LB 1 } 3 "$Index-prerace")) { throw 'pre-race menu not reached' }
    Tour-Press A 11
    Fm3 'env FM3_FREEZE_TIME 1' | Out-Null
}
Start-Sleep 5
Fm3 "shot $sp\lum-$Name.png" | Out-Null
$log = "$r\out\run\fm3.log"
$before = (Get-Content $log).Count
Fm3 'capture' | Out-Null
Fm3 'wait 3' | Out-Null
Start-Sleep 5
$lines = @(Get-Content $log | Select-Object -Skip $before)
# the final pass's vertex texture: vs:t17=?36 32x32@<addr>
$m = ($lines | Select-String 'ps 5b7efac9b0c87a00.*vs:t17=\S+ 32x32@([0-9A-F]+)' | Select-Object -First 1)
if ($m) {
    $addr = $m.Matches[0].Groups[1].Value
    "lum texture at $addr"
    $phys = '{0:X8}' -f ([Convert]::ToUInt32($addr, 16) + 0xA0000000)
    Fm3 'env FM3_WRITEBACK 32x32' | Out-Null
    Start-Sleep 3
    $peek = @(Fm3 "peek $phys 4096") + @(Fm3 "peek $addr 4096")
    $peek | Set-Content "$sp\lum-$Name.peek.txt"
    "peeked"
} else { 'final pass not found in the capture' }
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
