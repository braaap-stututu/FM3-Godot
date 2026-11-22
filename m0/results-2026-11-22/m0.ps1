# M0 runs on FM3's frozen grid (renderer replacement project). Dot-source, then: Invoke-M0Run 'R2' @{ ... }
. "$PSScriptRoot\..\..\..\..\FM3-ReGPU recomp\tools\perf_suite.ps1" -Run 'm0'

$script:M0Triple = @{ FM3_TRIPLE = '1'; FM3_VR = 'off'; FM3_RESOLUTION = '7680x1440' }

function Get-M0Lines([int]$N = 5) {
    $log = $Suite.Log
    $lite = Select-String -Path $log -Pattern 'perf lite: ([\d.]+) fps, ([\d.]+) ms/frame \(p99 ([\d.]+) ms.*\| ([\d.]+) draws/frame \| GPU ([\d.]+) ms/frame \| draw thread (-?[\d.]+)% busy' | Select-Object -Last $N
    $tri = Select-String -Path $log -Pattern 'triple: draws/frame: (\d+) centre and shared passes, (\d+) left, (\d+) right' | Select-Object -Last $N
    $hyp = Select-String -Path $log -Pattern 'hyper cull: (\d+) drawn, (\d+) skipped \(([\d.]+)%\)' | Select-Object -Last 3
    $script:M0Hyper = if ($hyp) { [math]::Round((($hyp | ForEach-Object { [double]$_.Matches[0].Groups[3].Value }) | Measure-Object -Average).Average, 1) } else { $null }
    $avg = { param($m, $g) [math]::Round((($m | ForEach-Object { [double]$_.Matches[0].Groups[$g].Value }) | Measure-Object -Average).Average, 2) }
    [pscustomobject]@{
        LiteFps   = if ($lite) { & $avg $lite 1 } else { $null }
        LiteP99   = if ($lite) { & $avg $lite 3 } else { $null }
        LiteDraws = if ($lite) { & $avg $lite 4 } else { $null }
        GpuMs     = if ($lite) { & $avg $lite 5 } else { $null }
        DrawBusy  = if ($lite) { & $avg $lite 6 } else { $null }
        Centre    = if ($tri) { & $avg $tri 1 } else { $null }
        Left      = if ($tri) { & $avg $tri 2 } else { $null }
        Right     = if ($tri) { & $avg $tri 3 } else { $null }
    }
}

function Invoke-M0Run([string]$Id, [hashtable]$Env, [int]$Samples = 12, [string]$Note = '') {
    $e = @{ REGPU_PERF_LITE = '1'; FM3_UPSCALER = 'off' }
    foreach ($k in $Env.Keys) { $e[$k] = $Env[$k] }
    $ok = Start-Grid $e 12
    if (-not $ok) { Write-Note "$Id : boot failed"; Stop-Game; return [pscustomobject]@{ Id = $Id; Ok = $false } }
    $gpuLine = (Select-String -Path $Suite.Log -Pattern 'gpu: ReGPU at' | Select-Object -Last 1).Line
    $triLine = (Select-String -Path $Suite.Log -Pattern 'triple: .*layout' | Select-Object -Last 1).Line
    $f = Get-Fps $Samples
    Start-Sleep 2
    $m = Get-M0Lines 5
    $r = [pscustomobject]@{
        Id = $Id; Ok = $true; Fps = $f.Fps; StatusDraws = $f.Draws; LiteFps = $m.LiteFps; P99 = $m.LiteP99; LiteDraws = $m.LiteDraws
        GpuMs = $m.GpuMs; DrawBusy = $m.DrawBusy; Centre = $m.Centre; Left = $m.Left; Right = $m.Right; HyperSkipPct = $script:M0Hyper
        Gpu = $gpuLine; Triple = $triLine
    }
    Add-Result $Id ($Env.Keys | ForEach-Object { "$_=$($Env[$_])" }) -join ' ' $f '' ("lite {0} fps p99 {1} draws {2} gpu {3} busy {4} C/L/R {5}/{6}/{7} {8}" -f $m.LiteFps, $m.LiteP99, $m.LiteDraws, $m.GpuMs, $m.DrawBusy, $m.Centre, $m.Left, $m.Right, $Note)
    Copy-Item $Suite.Log (Join-Path $Suite.Out "$Id.log") -Force
    Stop-Game
    $r
}
