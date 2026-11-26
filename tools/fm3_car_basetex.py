"""fm3_car_basetex.py: the car library's per-colour base textures (2026-11-26).

    python tools/fm3_car_basetex.py <cars dir (work/assets/cars)> <gamedb.slt> <library dir (out/cars)> [car ...]

Each Combo_Colors row names the colour's BaseTexture: most are nodamage.tga, but 44 of the 510 cars switch to another
for some colours (REN_5Turbo_80: colour 1 nodamage = red decals, 2 / 3 nodamageblue = blue, 4 nodamageblack), and the
library (fm3_car_library.py) exported only nodamage. This adds, beside a built library car:
  <car>_tex/<stem>.png, <stem>_lod0.png   the alternative texture as the library's xds materials use it
  <car>_tex/paint_over_white_<stem>.png    its lod0 composited over white, as the paint material uses it
  <car>_basetex.json                       {Sequence: stem} for the colours whose base is not nodamage
world_view.gd swaps the textures when it attaches a library car in such a colour.
"""
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
import fm3_tex  # noqa: E402


def base_textures(db, media):
    c = sqlite3.connect('file:' + db + '?mode=ro', uri=True)
    try:
        row = c.execute('select Id from Data_Car where lower(MediaName) = lower(?)', (media,)).fetchone()
        if not row:
            return {}
        return {int(s): (b or '').lower() for s, b in
                c.execute('select Sequence, BaseTexture from Combo_Colors where Ordinal = ?', (row[0],))}
    except sqlite3.Error:
        return {}


def main():
    a = sys.argv[1:]
    cdir, db, lib = a[:3]
    dbs = [db] + sorted(os.path.join(r, f) for r, _, fs in os.walk(os.path.join(os.path.dirname(os.path.abspath(cdir)), 'dlc_db'))
                        for f in fs if f.endswith('.slt'))
    cars = a[3:] or sorted(f[:-len('_colors.json')] for f in os.listdir(lib) if f.endswith('_colors.json'))
    done = 0
    for car in cars:
        bases = {}
        for d in dbs:
            bases = base_textures(d, car)
            if bases:
                break
        alt = {s: b[:-4] if b.endswith('.tga') else b for s, b in bases.items() if b and b != 'nodamage.tga'}
        if not alt:
            continue
        tdir = os.path.join(lib, car + '_tex')
        ok = {}
        for s, stem in alt.items():
            have = True
            for variant in (stem + '_lod0', stem):
                p = os.path.join(cdir, car, variant + '.xds')
                if not os.path.exists(p):
                    have = variant != stem + '_lod0' and have
                    continue
                img = fm3_tex.load_xds(p)
                out = os.path.join(tdir, variant + '.png')
                if not os.path.exists(out):
                    fr.write_png(out, img.shape[1], img.shape[0], np.ascontiguousarray(img).tobytes())
                if variant.endswith('_lod0'):
                    a_ = img[..., 3:4].astype(np.float32) / 255.0
                    over = np.concatenate([np.clip(img[..., :3] * a_ + 255.0 * (1.0 - a_), 0, 255).astype(np.uint8),
                                           np.full(img.shape[:2] + (1,), 255, np.uint8)], axis=2)
                    out = os.path.join(tdir, 'paint_over_white_' + stem + '.png')
                    if not os.path.exists(out):
                        fr.write_png(out, over.shape[1], over.shape[0], np.ascontiguousarray(over).tobytes())
            if have and os.path.exists(os.path.join(tdir, stem + '_lod0.png')):
                ok[s] = stem
        if ok:
            with open(os.path.join(lib, car + '_basetex.json'), 'w', newline='\n') as f:
                json.dump(ok, f)
            done += 1
            print(car, ok)
    print(f'{done} cars with per-colour base textures')


if __name__ == '__main__':
    main()
