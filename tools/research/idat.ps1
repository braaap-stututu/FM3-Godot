param([string]$Track, [string]$Points = '640,600')
Set-Location 'C:\claude code projects\handoff-2026-11-22\Godot\frame-ir'
$c = (Select-String -Path "out\live\tracks\$Track-godot.log" -Pattern 'live camera \[' | Select -First 1).Line
$m = [regex]::Match($c, 'Z: \(([-\d.e]+), ([-\d.e]+), ([-\d.e]+)\), O: \(([-\d.e]+), ([-\d.e]+), ([-\d.e]+)\)')
$z = 1..3 | % { [double]$m.Groups[$_].Value }; $o = 4..6 | % { [double]$m.Groups[$_].Value }
$at = "{0},{1},{2}" -f ($o[0] - 50 * $z[0]), ($o[1] - 50 * $z[1]), ($o[2] - 50 * $z[2])
$from = "{0},{1},{2}" -f $o[0], $o[1], $o[2]
$g = "..\Godot_v4.7.2-stable_win64_console.exe"
& $g --path godot -s res://viewer/world_view.gd -- --gltf "$PWD\out\world\$Track.gltf" --id --size 1280x720 --out "$PWD\out\world\${Track}_ids.png" --look-from $from --look-at $at 2>&1 | Out-Null
& $g --path godot -s res://viewer/world_view.gd -- --gltf "$PWD\out\world\$Track.gltf" --lit --size 1280x720 --out "$PWD\out\world\${Track}_lit.png" --look-from $from --look-at $at 2>&1 | Out-Null
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py -c "import sys, numpy as np; sys.path.insert(0,'tools'); import fir_frame; w,h,px=fir_frame.read_png('out/world/${Track}_ids.png'); a=np.frombuffer(bytes(px),np.uint8).reshape(h,w,-1).astype(int); names={int(l.split(' ',1)[0]): l.split(' ',1)[1] for l in open('out/world/${Track}_ids.png.ids.txt').read().splitlines()}; pts=[tuple(map(int,p.split(','))) for p in sys.argv[1].split(';')]; [print((x,y), names.get(int(a[y,x,0]+(a[y,x,1]<<8)),'?')) for x,y in pts]" $Points
