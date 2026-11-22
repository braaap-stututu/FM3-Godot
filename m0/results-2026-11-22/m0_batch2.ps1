# M0 part 2: 2-core runs of the capped configurations (R1, R2, R3, R7) + R8 races (triple, centre only).
param([string]$Out = "$PSScriptRoot\m0_results2.jsonl")
. "$PSScriptRoot\m0.ps1"
$msaa = @{ FM3_MSAA = '4' }
function Merge([hashtable[]]$hs) { $r = @{}; foreach ($h in $hs) { foreach ($k in $h.Keys) { $r[$k] = $h[$k] } }; $r }

# Affinity watcher: holds fm3 to 2 cores / 4 threads (mask 0x0F), as in the existing 2-core tests.
Get-Job -Name affinity -ErrorAction SilentlyContinue | Remove-Job -Force
Start-Job -Name affinity -ScriptBlock {
    $m = [IntPtr]0x0F
    $end = (Get-Date).AddMinutes(60)
    while ((Get-Date) -lt $end) {
        foreach ($p in Get-Process fm3 -ErrorAction SilentlyContinue) { try { if ($p.ProcessorAffinity -ne $m) { $p.ProcessorAffinity = $m } } catch {} }
        Start-Sleep -Milliseconds 300
    }
} | Out-Null

$runs = [ordered]@{
    'R1-2c' = Merge @($msaa, @{ FM3_TRIPLE = '0'; FM3_VR = 'off'; FM3_RESOLUTION = '2560x1440' })
    'R2-2c' = Merge @($msaa, $M0Triple)
    'R3-2c' = Merge @($msaa, $M0Triple, @{ REGPU_TRIPLE_CENTRE_ONLY = '1' })
    'R7-2c' = Merge @($msaa, $M0Triple, @{ REGPU_NO_RENDER = '1' })
}
foreach ($round in 0, 1) {
    $ids = @($runs.Keys); if ($round) { [array]::Reverse($ids) }
    foreach ($id in $ids) {
        $r = Invoke-M0Run "$id-r$round" $runs[$id] 12
        $r | Add-Member -NotePropertyName Run -NotePropertyValue $id -Force
        $r | Add-Member -NotePropertyName Round -NotePropertyValue $round -Force
        ($r | ConvertTo-Json -Compress) | Add-Content -Encoding utf8 $Out
        Write-Note ("{0} round {1}: fps {2} lite {3} gpu {4} busy {5}" -f $id, $round, $r.Fps, $r.LiteFps, $r.GpuMs, $r.DrawBusy)
    }
}
Get-Job -Name affinity -ErrorAction SilentlyContinue | Remove-Job -Force

# R8: races at full CPU, triple and centre only, 15 s with the throttle held, two boots each.
foreach ($round in 0, 1) {
    foreach ($v in @(@('R8-triple', (Merge @($msaa, $M0Triple))), @('R8-centre', (Merge @($msaa, $M0Triple, @{ REGPU_TRIPLE_CENTRE_ONLY = '1' }))))) {
        $id = $v[0]; $e = @{ REGPU_PERF_LITE = '1'; FM3_UPSCALER = 'off' }; foreach ($k in $v[1].Keys) { $e[$k] = $v[1][$k] }
        if (-not (Start-Grid $e 12)) { Write-Note "$id boot failed"; Stop-Game; continue }
        $m = Test-Drive "$id-r$round" $id 15
        $ft = Select-String -Path $Suite.Log -Pattern 'triple: draws/frame: (\d+) centre and shared passes, (\d+) left, (\d+) right' | Select-Object -Last 3
        $lite = Select-String -Path $Suite.Log -Pattern 'perf lite: ([\d.]+) fps, ([\d.]+) ms/frame \(p99 ([\d.]+) ms.*\| ([\d.]+) draws/frame \| GPU ([\d.]+) ms/frame \| draw thread (-?[\d.]+)% busy' | Select-Object -Last 8
        $obj = [pscustomobject]@{ Run = $id; Round = $round; Fps = $m.Fps; Draws = $m.Draws; Samples = $m.Samples
            LiteLines = ($lite | ForEach-Object { $_.Line -replace '^\[\s*[\d.]+\]\s*', '' }) ; TripleLines = ($ft | ForEach-Object { $_.Line }) }
        ($obj | ConvertTo-Json -Compress -Depth 3) | Add-Content -Encoding utf8 $Out
        Copy-Item $Suite.Log (Join-Path $Suite.Out "$id-r$round.log") -Force
        Stop-Game
    }
}
Write-Note 'M0 part 2 done'
