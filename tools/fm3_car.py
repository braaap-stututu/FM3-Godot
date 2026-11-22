"""fm3_car.py: whole FM3 cars from their .carbin files (Media/Cars/<car>.zip, extracted with tools/fm3unzip).

Layout (big-endian), worked out on the CR-X against the captured grid frame (every captured car draw's index and vertex
data are verbatim in the file):
  part section: ... f32[3] offset (car space, at name - 81), f32[3] bbox min, f32[3] bbox max, ..., u32 name length,
      name (e.g. body, trunk, bumperRa, skirtLb, wingrace, glassLM), u32 2, u32 vertex count, u32 stride (40),
      vertices, then its subsections;
  vertex (stride 40): half4 position (x, y, z, w: car space = xyz * w + section offset, as the vertex shader's
      'mad r4 = r1.xyz * r1.w + c190'), half2 UV0 at byte 8 (the captured texture coordinates, unchanged), the rest
      packed normal / tangent / damage data (not used here);
  subsection: u32 2, u32 name length, material name (body, window, chrome, ...), u32 1 (LOD), u32 index type (6 strip /
      4 list), u32 material index, u32 1, u32 0 x4, f32 1.0 x4, f32[2] UV offset, f32[2] UV tile, u32 3, i32 index
      count, i32 index size, indices (0xFFFF restarts).
Part variants: a base name plus a lower-case letter (bumperRa .. bumperRf, skirtLa ..) or 'race'; the stock car uses one
variant per part group (the captured frame shows which).
"""
import re
import struct

import numpy as np

_SEC = re.compile(rb'\x00\x00\x00([\x03-\x30])([A-Za-z][A-Za-z0-9_]{2,47})\x00\x00\x00\x02')
_SUB = re.compile(rb'\x00\x00\x00\x02\x00\x00\x00([\x04-\x40])([a-z][a-z0-9_]{3,63})\x00\x00\x00\x01')


HEADER = bytes([0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2])


def _header_offset(data, o, lo):
    """The part's car-space offset: the last header between the previous part's data (lo) and this part's name:
    u32 2, u32 0, u32 0, u32 2, f32[3] offset, f32[3] bbox min, f32[3] bbox max (for glass panes thousands of bytes
    before the name, after their damage data). None if there is none."""
    p = data.rfind(HEADER, lo, o)
    if p < 0:
        return None
    v = np.array(struct.unpack_from('>9f', data, p + 16))
    if np.all(np.isfinite(v)) and np.abs(v).max() < 10 and np.all(v[3:6] <= v[6:9]):
        return v[:3]
    return None


def parse(data):
    """[{'name', 'offset' (3,), 'positions' (n, 3) car space, 'uv0' (n, 2), 'raw', 'subs': [{'material', 'prim',
    'indices', 'ib_hex'}]}]"""
    secs = []
    for m in _SEC.finditer(data):
        if m.group(1)[0] != len(m.group(2)):
            continue
        q = m.start() + 4 + len(m.group(2))
        two, cnt, st = struct.unpack_from('>III', data, q)
        if not (16 <= st <= 64 and 0 < cnt < 200000) or q + 12 + cnt * st > len(data):
            continue
        o = m.start()
        off = _header_offset(data, o, secs[-1]['end'] if secs else 0)
        raw = np.frombuffer(data, np.uint8, cnt * st, q + 12).reshape(cnt, st)
        h = raw[:, :8].copy().view('>f2').reshape(cnt, 4).astype(np.float64)
        uv = raw[:, 8:12].copy().view('>f2').reshape(cnt, 2).astype(np.float64)
        secs.append({'name': m.group(2).decode(), 'start': o, 'end': q + 12 + cnt * st, 'offset': off,
                     'local': h[:, :3] * h[:, 3:4], 'uv0': uv, 'subs': []})
    starts = [s['end'] for s in secs]
    import bisect
    for m in _SUB.finditer(data):
        if m.group(1)[0] != len(m.group(2)):
            continue
        q = m.start() + 8 + len(m.group(2))
        lod, prim = struct.unpack_from('>II', data, q)
        three, cnt, sz = struct.unpack_from('>Iii', data, q + 4 * 16)
        if three != 3 or sz not in (2, 4) or not 0 < cnt < 4000000:
            continue
        k = bisect.bisect_right(starts, m.start()) - 1
        if k < 0:
            continue
        io = q + 4 * 19
        idx = np.frombuffer(data, '>u2' if sz == 2 else '>u4', cnt, io).astype(np.int64)
        secs[k]['subs'].append({'material': m.group(2).decode(), 'prim': prim, 'indices': idx,
                                'ib_hex': data[io:io + cnt * sz].hex()})
    return secs


def triangles(indices, prim, restart=0xFFFF):
    if prim == 4:
        n = len(indices) // 3 * 3
        return indices[:n].reshape(-1, 3)
    tris, run = [], []
    for v in list(indices) + [restart]:
        if v == restart or v == 0xFFFFFFFF:
            for k in range(len(run) - 2):
                a, b, c = run[k], run[k + 1], run[k + 2]
                if a != b and b != c and a != c:
                    tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
            run = []
        else:
            run.append(int(v))
    return np.array(tris, np.int64).reshape(-1, 3)


_VAR = re.compile(r'^(.*?[LR]?)([a-g]|race)$')


def group_of(name):
    """(part group, variant) for variant parts (bumperRa -> ('bumperR', 'a'), wingrace -> ('wing', 'race')), else
    (name, None)."""
    m = _VAR.match(name)
    if m and m.group(1) and m.group(1) not in ('', ) and not name.startswith(('glass', 'seat', 'mirror', 'head', 'tail')):
        return m.group(1), m.group(2)
    return name, None


def stock_parts(secs, captured):
    """Section names of the car as the game shows it: every non-variant part, and per variant group the captured
    variant (or its mirror's: skirtLa from skirtRa), else 'a'; optional extras (wings, cages) only when captured."""
    chosen = {}
    for s in secs:
        g, v = group_of(s['name'])
        if v is None:
            continue
        if s['name'] in captured and v != 'race':
            chosen[g] = v
    keep = set(n for n in captured)
    for s in secs:
        g, v = group_of(s['name'])
        if v is None:
            if s['name'] in captured or not s['name'].endswith('race'):
                keep.add(s['name'])
            continue
        mirror = g[:-1] + {'L': 'R', 'R': 'L'}[g[-1]] if g[-1:] in ('L', 'R') else None
        want = chosen.get(g) or (chosen.get(mirror) if mirror else None)
        if want is None and not g.startswith(('wing', 'cage')):
            want = 'a'
        if want is not None and v == want:
            keep.add(s['name'])
    return keep


def kabsch(x, y, allow_mirror=True):
    """R, t with y ~ x R^T + t (least squares, scale 1)."""
    mx, my = x.mean(0), y.mean(0)
    H = (x - mx).T @ (y - my)
    U, _, Vt = np.linalg.svd(H)
    best = None
    for sgn in ((1, -1) if allow_mirror else (1,)):
        D = np.diag([1.0, 1.0, sgn * np.sign(np.linalg.det(Vt.T @ U.T))])
        R = Vt.T @ D @ U.T
        t = my - R @ mx
        e = np.abs(x @ R.T + t - y).max()
        if best is None or e < best[2]:
            best = (R, t, e)
    return best
