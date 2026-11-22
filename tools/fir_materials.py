#!/usr/bin/env python3
"""fir_materials.py: inventory of a captured frame's pixel shaders, as input for per-game material rules.

    python fir_materials.py capture.fir [--top N]

Per pixel shader (by draw count in the scene pass): its texture fetches in order (slot, dimension, coordinate source
register) and, from the draws, each slot's texture: format, size, whether the tap decoded it (decoded = a texture from
memory; not decoded = usually a render target the game made earlier in the frame: shadow maps, reflections) and the
mean RGBA. This is what a profile needs to map shaders to material archetypes (SCENE_API.md) with texture roles.
"""
import os
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
from fir_frame import load_vs_code  # noqa: E402
from fir_world import scene_range  # noqa: E402
from fir_xenos import bits, parse  # noqa: E402

DIMS = ('1D', '2D', '3D', 'cube')


def tfetches(code):
    words, cfs = parse(code, full=True)
    out = []
    for lo, hi in cfs:
        if (hi >> 12) & 15 not in (1, 2, 3, 4, 5, 6, 13, 14):
            continue
        addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
        for k in range(count):
            i = addr + k
            w = words[i * 3:i * 3 + 3]
            if (seq >> (2 * k)) & 1 and bits(w[0], 0, 5) == 1:
                f = (bits(w[0], 20, 5), DIMS[bits(w[2], 14, 2)], bits(w[0], 5, 6))
                if f not in out:
                    out.append(f)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 25
    cap = fr.Capture(path)
    ps = load_vs_code(path, pixel=True)
    frame = cap.frames[0]
    lo, hi = scene_range(frame)
    by_ps = defaultdict(list)
    for d in cap.draws(frame):
        if lo < d['seq'] < hi:
            by_ps[d['ps']].append(d)
    print(f"frame {frame['index']}: {sum(len(v) for v in by_ps.values())} scene-pass draws, {len(by_ps)} pixel shaders")
    for h, ds in sorted(by_ps.items(), key=lambda kv: -len(kv[1]))[:top]:
        fetch = tfetches(ps[h]) if h in ps else []
        print(f'\nps {h:016x}: {len(ds)} draws (vs: {len(set(d["vs"] for d in ds))} distinct), fetches ' +
              ', '.join(f's{s} {dim} <- r{src}' for s, dim, src in fetch))
        slots = sorted(set(s for s, _, _ in fetch))
        for s in slots:
            seen = Counter()
            sample = None
            for d in ds:
                t = next((t for t in d['texs'] if t[0] == s), None)
                if t is None:
                    continue
                tex = cap.data.get((3, t[8], t[9]))
                seen[(t[3] & 0x3F, bool(tex))] += 1
                if tex and sample is None:
                    sample = tex
            desc = ', '.join(f'format {f} {"decoded" if dec else "not decoded"} x{n}' for (f, dec), n in seen.most_common())
            if sample is not None:
                a = np.frombuffer(sample['bytes'][:sample['w'] * sample['h'] * 4], np.uint8).reshape(-1, 4)
                desc += f'; e.g. {sample["w"]}x{sample["h"]} mean rgba {a.mean(0).round().astype(int).tolist()}'
            print(f'  s{s}: {desc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
