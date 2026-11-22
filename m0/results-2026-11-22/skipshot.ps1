# Frozen grid, single screen: a screenshot, then the same with one vertex shader's draws skipped (REGPU_SKIP_SHADERS, live).
param([string]$Hash, [string]$OutA, [string]$OutB)
. "$PSScriptRoot\m0.ps1"
$e = @{ REGPU_PERF_LITE = '1'; FM3_UPSCALER = 'off'; FM3_MSAA = '4'; FM3_TRIPLE = '0'; FM3_RESOLUTION = '2560x1440' }
if (-not (Start-Grid $e 8)) { 'boot failed'; Stop-Game; return }
function Shot([string]$p) {
    Remove-Item $p -ErrorAction SilentlyContinue
    Fm3 "shot $p" | Out-Null
    for ($i = 0; $i -lt 50 -and -not (Test-Path $p); $i++) { Start-Sleep -Milliseconds 100 }
    Start-Sleep -Milliseconds 300
}
Shot $OutA
Fm3 "env REGPU_SKIP_SHADERS $Hash" | Out-Null
Start-Sleep -Milliseconds 500
Shot $OutB
Stop-Game
"A: $(Test-Path $OutA)  B: $(Test-Path $OutB)"
