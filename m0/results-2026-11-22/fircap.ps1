# Frozen-grid Frame IR capture: boots the grid with the tap available, arms it, waits for the "capture ... done" line.
param([string]$Out, [int]$Frames = 3, [string]$Mode = 'triple')
. "$PSScriptRoot\m0.ps1"
$e = @{ REGPU_PERF_LITE = '1'; FM3_UPSCALER = 'off'; FM3_MSAA = '4'; REGPU_FIR_CAPTURE = $Out; REGPU_FIR_FRAMES = "$Frames" }
if ($Mode -eq 'triple') { foreach ($k in $M0Triple.Keys) { $e[$k] = $M0Triple[$k] } } else { $e['FM3_TRIPLE'] = '0'; $e['FM3_RESOLUTION'] = '2560x1440' }
Remove-Item $Out -ErrorAction SilentlyContinue
if (-not (Start-Grid $e 8)) { 'boot failed'; Stop-Game; return }
$t0 = Get-Date
Fm3 'switch REGPU_FIR_ARM 1' | Out-Null
while (((Get-Date) - $t0).TotalSeconds -lt 120) {
    Start-Sleep 1
    $done = Select-String -Path $Suite.Log -Pattern 'fir tap: capture \d+ done' | Select-Object -Last 1
    if ($done) { break }
}
Select-String -Path $Suite.Log -Pattern 'fir tap:' | ForEach-Object { $_.Line }
$f = Get-Fps 4
"fps after capture: $($f.Fps)"
Copy-Item $Suite.Log ([IO.Path]::ChangeExtension($Out, '.log')) -Force
Stop-Game
if (Test-Path $Out) { "file: {0:N1} MB" -f ((Get-Item $Out).Length / 1MB) }
