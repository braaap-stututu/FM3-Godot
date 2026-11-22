# Game-logic CPU in an AI race without ReGPU drawing: per-thread CPU (threads.ps1) during a 20 s drive.
param([string]$Sample = '', [int]$DriveSeconds = 20, [string]$Tag = 'threads', [string]$Mask = '')
. "$PSScriptRoot\m0.ps1"
$e = @{ FM3_MSAA = '4'; FM3_TRIPLE = '0'; FM3_VR = 'off'; FM3_RESOLUTION = '2560x1440'; REGPU_NO_RENDER = '1'; REGPU_PERF_LITE = '1'; FM3_UPSCALER = 'off' }
if ($Sample) { $e['FM3_SAMPLE_THREAD'] = $Sample; $e['FM3_SAMPLE_CALLERS'] = '1' }
if ($Mask) { Get-Job -Name affinity -ErrorAction SilentlyContinue | Remove-Job -Force; Start-Job -Name affinity -ArgumentList $Mask -ScriptBlock { param($m) $m = [IntPtr][Convert]::ToInt64($m, 16); $end = (Get-Date).AddMinutes(10); while ((Get-Date) -lt $end) { foreach ($p in Get-Process fm3 -ErrorAction SilentlyContinue) { try { if ($p.ProcessorAffinity -ne $m) { $p.ProcessorAffinity = $m } } catch {} }; Start-Sleep -Milliseconds 300 } } | Out-Null }
if (-not (Start-Grid $e 8)) { 'boot failed'; Stop-Game; return }
$job = Start-Job -ScriptBlock { param($d) Start-Sleep 4; & 'G:\claude code projects\FM3-ReGPU recomp\tools\perf\threads.ps1' -Seconds ($d - 6) -Top 20 } -ArgumentList $DriveSeconds
$m = Test-Drive "game-$Tag" 'norender' $DriveSeconds
$threads = Receive-Job $job -Wait -AutoRemoveJob
"drive: $($m.Fps) fps"
$threads | Format-Table -AutoSize | Out-String -Width 200
Copy-Item $Suite.Log (Join-Path $Suite.Out "game-$Tag.log") -Force
if ($Sample) { Select-String -Path $Suite.Log -Pattern 'profile:' | Select-Object -Last 40 | ForEach-Object { $_.Line } }
Stop-Game

Get-Job -Name affinity -ErrorAction SilentlyContinue | Remove-Job -Force
