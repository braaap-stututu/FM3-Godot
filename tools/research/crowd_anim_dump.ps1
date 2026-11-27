# crowd_anim_dump.ps1 (2026-11-27; LIVE.md "The crowd's animations"): boots FM3's grid test (CrownJewel), captures a
# frame and reads the crowd's baked animation buffer (vs 6ee601730a7f9f87's vertex fetch 94: 1,201,992 bytes, every
# seated and standing animation of spectators.xml, built by the game at the race load) through the debug server into
# Godot\work\crowd_anim\crowdbuf.bin (game data: not committed). Then: python tools/fm3_crowd_anim.py.
#     powershell -ExecutionPolicy Bypass -File frame-ir\tools\research\crowd_anim_dump.ps1
$ErrorActionPreference = 'Continue'
$godot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$r = Join-Path (Split-Path -Parent $godot) 'FM3-ReGPU recomp'
$sp = Join-Path $godot 'work\crowd_anim'
New-Item -ItemType Directory -Force $sp | Out-Null
if (Get-Process fm3 -ErrorAction SilentlyContinue) { throw 'fm3 is running' }
$log = "$r\out\run\fm3.log"; $t0 = Get-Date
$env:FM3_GRID_TEST = '1'; $env:FM3_MINIMIZED = '1'
Start-Process cmd.exe "/c `"$r\play.cmd`"" -WindowStyle Hidden
while (((Get-Date) - $t0).TotalSeconds -lt 180) { Start-Sleep 3; if ((Test-Path $log) -and (Get-Item $log).LastWriteTime -gt $t0 -and ((Get-Content $log -Raw) -match 'grid test: frozen')) { break } }
foreach ($v in 'FM3_GRID_TEST', 'FM3_MINIMIZED') { Set-Item "Env:$v" '' }
. "$r\tools\fm3ctl.ps1"
Start-Sleep 3
Fm3 "env REGPU_TRACE_VC 1" | Out-Null
$before = (Get-Content $log).Count
Fm3 "capture" | Out-Null
Start-Sleep 6
$cap = Get-Content $log | Select-Object -Skip $before
$line = $cap | Select-String 'vf94: ([0-9A-F]{8}) size 1201992' | Select-Object -First 1
$addr = [Convert]::ToUInt32($line.Matches[0].Groups[1].Value, 16)
"buffer at {0:X8}" -f $addr
$fs = [System.IO.File]::Create("$sp\crowdbuf.bin")
for ($o = 0; $o -lt 1201992; $o += 4096) {
    $n = [Math]::Min(4096, 1201992 - $o)
    # (the fetch address is physical: read through the A0000000 mirror; 2684354560 = 0xA0000000, a negative literal
    # in PowerShell)
    $res = Fm3 ("peek {0:X8} {1}" -f ([uint32]$addr + [uint32]2684354560 + $o), $n)
    $hex = ($res | Out-String) -replace '(?s).*"hex":"([0-9A-F]*)".*', '$1'
    $bytes = New-Object byte[] ($hex.Length / 2)
    for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($hex.Substring(2 * $i, 2), 16) }
    $fs.Write($bytes, 0, $bytes.Length)
}
$fs.Close()
"$((Get-Item "$sp\crowdbuf.bin").Length) bytes -> $sp\crowdbuf.bin"
Get-Process fm3 -ErrorAction SilentlyContinue | % { $_.CloseMainWindow() | Out-Null }
Start-Sleep 8
Get-Process fm3 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
