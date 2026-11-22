#!/usr/bin/env python3
"""fir_pick.py: which draws cover a screen pixel of a captured frame (nearest first), with shaders and textures.

    python fir_pick.py capture.fir x,y [x,y ...] [--size 1280x720]

x, y are pixels of the final screen (as in a screenshot scaled to --size, default 1280x720). Scene-pass draws are
taken through FM3's 180-degree rotation (as fir_frame.py --flip-scene). For material work: point at a surface that
looks wrong, get the pixel shader to write a rule for (profiles/fm3/materials.json).
"""
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings('ignore')
import fir_read as fr  # noqa: E402
from fir_frame import load_vs_code, place  # noqa: E402
from fir_geometry import load_shader_layouts  # noqa: E402
from fir_world import scene_range  # noqa: E402


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path = sys.argv[1]
    sw, sh = (1280, 720)
    if '--size' in sys.argv:
        sw, sh = map(int, sys.argv[sys.argv.index('--size') + 1].split('x'))
    points = [tuple(map(float, a.split(','))) for a in sys.argv[2:] if ',' in a and not a.startswith('-')]
    cap = fr.Capture(path)
    load_shader_layouts(cap, path)
    code = load_vs_code(path)
    frame = cap.frames[0]
    with np.errstate(all='ignore'):
        draws, placed, why, kinds = place(cap, path, code, frame)
    lo, hi = scene_range(frame)
    for px, py in points:
        x, y = px * 1280 / sw, py * 720 / sh
        hits = []
        for d, regs, g, pv, mi in placed:
            if not (lo < d['seq'] < hi):
                continue
            tris = np.array(g['triangles'])
            if not len(tris):
                continue
            c = np.array([v if v is not None else (np.nan,) * 4 for v in pv], dtype=np.float64)
            w = c[:, 3]
            sx = 1280 - (c[:, 0] / w * 640 + 640)
            sy = 720 - (c[:, 1] / w * -360 + 360)
            a, b, cc = tris[:, 0], tris[:, 1], tris[:, 2]
            ok = (w[a] > 0.05) & (w[b] > 0.05) & (w[cc] > 0.05)
            if not ok.any():
                continue
            ax, ay, bx, by, cx, cy = sx[a], sy[a], sx[b], sy[b], sx[cc], sy[cc]
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            with np.errstate(all='ignore'):
                l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
                l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
            l3 = 1 - l1 - l2
            inside = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0) & np.isfinite(den) & (den != 0)
            if inside.any():
                k = np.nonzero(inside)[0]
                depth = (l1[k] * w[a[k]] + l2[k] * w[b[k]] + l3[k] * w[cc[k]]).min()
                hits.append((depth, d))
        hits.sort(key=lambda t: t[0])
        print(f'pixel ({px:g}, {py:g}): {len(hits)} draws')
        for depth, d in hits[:6]:
            texs = ' '.join(f"s{t[0]}:f{t[3] & 0x3F}{'' if (3, t[8], t[9]) in cap.data else '(rt)' if t[1] & 2 else '(-)'}"
                            for t in d['texs'])
            print(f"  depth {depth:7.2f}  draw {d['seq']:5d}  vs {d['vs']:016x}  ps {d['ps']:016x}  {texs}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
