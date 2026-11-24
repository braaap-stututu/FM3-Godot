# add_cars.ps1: cars into the car library (out\cars) from the game's own zips (2026-11-24).
#
#   powershell -ExecutionPolicy Bypass -File frame-ir\tools\add_cars.ps1 [-Log <viewer log>] [-Cars NAME,NAME]
#
# -Log: a world_view log; every "live car .. is NAME: no library model" names a car to add. Each car's zip
# (Media\Cars\<NAME>.zip) unpacks to work\assets\cars\<name>, its stock wheels (Media\Wheels\<NAME>.zip) to
# work\assets\wheelzips\<name> (tools\fm3unzip), then tools\fm3_car_library.py builds them. Disc 2's cars (8 packages
# the recomp installs to <FM3>\out\user\dlc; Free Play opponents come from them too) are folders media/cars/<NAME>/ and
# media/wheels/<NAME>/ inside each package's Media\DLCZips\*_pri_65.zip: extracted from there when disc 1 has no zip.
param([string]$Log = '', [string[]]$Cars = @(),
    [string]$Fm3 = '')
$ErrorActionPreference = 'Continue'
if (-not $Fm3) { $Fm3 = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))) 'FM3-ReGPU recomp' }
$repo = Split-Path -Parent $PSScriptRoot
$godotDir = Split-Path -Parent $repo
$media = Join-Path $Fm3 'reference\rexglue recomp reference\hl360-forza3\game\disc1\Media'
$db = Join-Path $Fm3 'Project Forza Plus 3\Main Game Changes\Media\DB\gamedb.slt'
$unzip = Join-Path $repo 'tools\fm3unzip\fm3unzip.exe'
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$names = @($Cars | % { $_ -split '[,\s]+' })
if ($Log -and (Test-Path $Log)) {
    $names += Select-String -Path $Log -Pattern 'is (\S+): no library model' | % { $_.Matches[0].Groups[1].Value }
}
$names = $names | Where-Object { $_ } | Sort-Object -Unique
# Disc 2: which package zip holds which car (keyed lower case; the value keeps the zip's own spelling)
$dlc = @{}
$dlcZips = @(Get-ChildItem (Join-Path $Fm3 'out\user\dlc') -Recurse -Filter '*_pri_65.zip' -ErrorAction SilentlyContinue | % FullName)
if ($dlcZips) {
    $code = "import sys, zipfile`nfor z in sys.argv[1:]:`n    for c in sorted({n.split('/')[2] for n in zipfile.ZipFile(z).namelist() if n.lower().startswith('media/cars/') and n.count('/') >= 3}):`n        print(z + '|' + c)"
    foreach ($l in (& $py -c $code @dlcZips)) { $zp, $cn = $l -split '\|'; $dlc[$cn.ToLower()] = @($zp, $cn) }
    # their database patches (media\db\patch\*_merge.slt: Disc 2 cars' colours, fm3_car_library.EXTRA_DBS)
    $dbDir = Join-Path $godotDir 'work\assets\dlc_db'
    if (-not (Test-Path $dbDir)) { foreach ($z in $dlcZips) { & $unzip $z $dbDir 'merge.slt' | Out-Null } }
}
$built = @()
foreach ($n in $names) {
    $lower = $n.ToLower()
    $cdir = Join-Path $godotDir "work\assets\cars\$lower"
    $wdir = Join-Path $godotDir "work\assets\wheelzips\$lower"
    $zip = Join-Path $media "Cars\$n.zip"
    if (-not (Test-Path $zip)) { $zip = Get-ChildItem (Join-Path $media 'Cars') -Filter "$n.zip" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
    if ((-not $zip -or -not (Test-Path $zip)) -and $dlc.ContainsKey($lower)) {
        $zp, $cn = $dlc[$lower]
        $tmp = Join-Path $godotDir "work\assets\dlc_tmp\$lower"
        foreach ($kind in 'cars', 'wheels') {
            $dst = if ($kind -eq 'cars') { $cdir } else { $wdir }
            if (Test-Path $dst) { continue }
            & $unzip $zp $tmp "media/$kind/$lower/" | Out-Null  # (fm3unzip matches its filter against lower-case names)
            if (Test-Path "$tmp\media\$kind\$cn") { Move-Item "$tmp\media\$kind\$cn" $dst }
        }
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        if (Test-Path $cdir) { $built += $lower }
        continue
    }
    if (-not $zip -or -not (Test-Path $zip)) { "$n : no car zip in Media\Cars nor in Disc 2's packages"; continue }
    if (-not (Test-Path $cdir)) { & $unzip $zip $cdir | Out-Null }
    $wzip = Join-Path $media "Wheels\$n.zip"
    if ((Test-Path $wzip) -and -not (Test-Path $wdir)) { & $unzip $wzip $wdir | Out-Null }
    $built += $lower
}
if ($built) {
    & $py (Join-Path $repo 'tools\fm3_car_library.py') (Join-Path $godotDir 'work\assets\cars') (Join-Path $godotDir 'work\assets\wheelzips') $db (Join-Path $repo 'out\cars') @built
}
