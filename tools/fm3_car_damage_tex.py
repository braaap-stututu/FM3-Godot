"""fm3_car_damage_tex.py: each library car's crash-damage texture as PNG (2026-11-27, LIVE.md "Crash damage").

    python tools/fm3_car_damage_tex.py <car files dir> <car library dir> [car ...]

Writes <library>/<car>_tex/damage_lod0.png from <car files>/<car>/damage_lod0.xds (RGBA as stored: grey scuffs and
scratches, alpha = how much they cover). The game's paint pixel shader (e41e183a423e6f1b) blends it by the vertex's
damage amount a (the lattice, fetch 94): colour = base x (1 - D.a x a) + D.rgb x a, and its highlight x (1 - a); the
viewer's fm3_carpaint.gdshader does the same (damage_tex). Cars whose PNG exists are skipped (--force rewrites).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
import fm3_tex  # noqa: E402


def main():
    a = sys.argv[1:]
    force = '--force' in a
    a = [x for x in a if x != '--force']
    if len(a) < 2:
        print(__doc__)
        return 2
    cdir, lib = a[:2]
    cars = a[2:] or sorted(os.path.splitext(f)[0] for f in os.listdir(lib) if f.endswith('.gltf'))
    n = 0
    for car in cars:
        src = os.path.join(cdir, car, 'damage_lod0.xds')
        out = os.path.join(lib, car + '_tex', 'damage_lod0.png')
        if not os.path.exists(src) or not os.path.isdir(os.path.dirname(out)) or (os.path.exists(out) and not force):
            continue
        img = fm3_tex.load_xds(src)
        fr.write_png(out, img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
        n += 1
    print(f'{n} damage textures written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
