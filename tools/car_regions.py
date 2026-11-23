"""Car paint and glass, the game against Godot: per car and material, the mean colour of each image inside that
material's pixels (from a world_view.gd --id render of the same view), and their difference.

    python tools/car_regions.py <game.png> <godot.png> <ids.png> [--groups body,glass] [--erode 2]

<ids.png>.ids.txt (written by --id) names each flat colour's mesh; car meshes are carbin_<car>_<material>_<n>.
Groups: body = paint ('body', 'body_2'), glass = 'window', 'glass', 'black_glass*' (car windows). Prints, per car and
group: pixels, game mean RGB (0-255), Godot mean RGB, mean |diff|, and the 10th/50th/90th luminance percentiles of
each (how much the reflections spread the colour).
"""
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_frame  # noqa: E402

GROUPS = {'body': ('body', 'body_2'), 'glass': ('window', 'glass', 'black_glass', 'black_glass_breakable')}


def load(p):
    w, h, px = fir_frame.read_png(p)
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, -1)[:, :, :3].astype(np.float64)


def main():
    a = sys.argv[1:]
    erode = int(a[a.index('--erode') + 1]) if '--erode' in a else 2
    groups = a[a.index('--groups') + 1].split(',') if '--groups' in a else list(GROUPS)
    game, godot, ids = load(a[0]), load(a[1]), load(a[2])
    names = {}
    for line in open(a[2] + '.ids.txt').read().splitlines():
        k, _, nm = line.partition(' ')
        names[int(k)] = nm
    key = (ids[:, :, 0].astype(np.int64) + (ids[:, :, 1].astype(np.int64) << 8))
    ok_b = np.abs(ids[:, :, 2] - 77) < 1  # (the id colour's blue is 77; edges blended with other colours are not)
    regions = {}
    for k, nm in names.items():
        m = re.match(r'carbin_([a-z0-9]+_[a-z0-9]+_\d+)_(.+)_\d+$', nm)
        if not m:
            continue
        for g in groups:
            if m.group(2) in GROUPS[g]:
                regions.setdefault((m.group(1), g), []).append(k)
    lum = np.array([0.2126, 0.7152, 0.0722])
    total = {}
    print(f'{"car":22s} {"group":6s} {"pixels":>7s}  {"game RGB":>16s}  {"godot RGB":>16s}  diff   game lum p10/50/90   godot lum p10/50/90')
    for (car, g), ks in sorted(regions.items()):
        mask = np.isin(key, ks) & ok_b
        for _ in range(erode):  # erode: a pixel stays when its 4 neighbours are in the mask too
            mask = mask & np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1)
        n = int(mask.sum())
        if n < 30:
            continue
        ga, go = game[mask], godot[mask]
        lg, lo = ga @ lum, go @ lum
        # (per car equally, so the big near CR-X does not outweigh the far cars)
        t_ = total.setdefault(g, [0.0, 0, 0.0])
        t_[0] += np.abs(ga - go).mean()
        t_[1] += 1
        t_[2] += abs(np.median(lg) - np.median(lo))
        print(f'{car:22s} {g:6s} {n:7d}  {np.round(ga.mean(0)).astype(int)!s:>16s}  {np.round(go.mean(0)).astype(int)!s:>16s}  '
              f'{np.abs(ga - go).mean():5.1f}  {np.percentile(lg, 10):5.0f} {np.percentile(lg, 50):4.0f} {np.percentile(lg, 90):4.0f}'
              f'       {np.percentile(lo, 10):5.0f} {np.percentile(lo, 50):4.0f} {np.percentile(lo, 90):4.0f}')
    for g, (d, n, m) in total.items():
        print(f'summary {g}: mean |diff| per car {d / n:.1f}, median luminance off by {m / n:.1f} ({n} cars)')


if __name__ == '__main__':
    main()
