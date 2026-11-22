# M0 batch: R1-R7, $Rounds boots each, order alternating per round. Results: results JSON lines + summary.
param([int]$Rounds = 2, [string]$Out = "$PSScriptRoot\m0_results.jsonl")
. "$PSScriptRoot\m0.ps1"
$msaa = @{ FM3_MSAA = '4' }
function Merge([hashtable[]]$hs) { $r = @{}; foreach ($h in $hs) { foreach ($k in $h.Keys) { $r[$k] = $h[$k] } }; $r }
$runs = [ordered]@{
    'R1' = Merge @($msaa, @{ FM3_TRIPLE = '0'; FM3_VR = 'off'; FM3_RESOLUTION = '2560x1440' })
    'R2' = Merge @($msaa, $M0Triple)
    'R3' = Merge @($msaa, $M0Triple, @{ REGPU_TRIPLE_CENTRE_ONLY = '1' })
    'R4' = Merge @($msaa, $M0Triple, @{ FM3_RESOLUTION = '3840x720' })
    'R5' = Merge @($msaa, $M0Triple, @{ REGPU_HYPER_CULL_PIXELS = '0' })
    'R6' = Merge @($msaa, $M0Triple, @{ REGPU_NO_GPU_WORK = '1' })
    'R7' = Merge @($msaa, $M0Triple, @{ REGPU_NO_RENDER = '1' })
}
$ids = @($runs.Keys)
for ($round = 0; $round -lt $Rounds; $round++) {
    $order = if ($round % 2) { [array]::Reverse($ids.Clone()); $x = $ids.Clone(); [array]::Reverse($x); $x } else { $ids }
    foreach ($id in $order) {
        $r = Invoke-M0Run "$id-r$round" $runs[$id] 12
        $r | Add-Member -NotePropertyName Run -NotePropertyValue $id -Force
        $r | Add-Member -NotePropertyName Round -NotePropertyValue $round -Force
        ($r | ConvertTo-Json -Compress) | Add-Content -Encoding utf8 $Out
        Write-Note ("{0} round {1}: fps {2} lite {3} gpu {4} busy {5} C/L/R {6}/{7}/{8} hyper {9}" -f $id, $round, $r.Fps, $r.LiteFps, $r.GpuMs, $r.DrawBusy, $r.Centre, $r.Left, $r.Right, $r.HyperSkipPct)
    }
}
Write-Note 'M0 batch done'
