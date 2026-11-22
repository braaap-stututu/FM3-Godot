#!/usr/bin/env python3
"""fir_frame.py: rebuild a captured frame's main view offline and check it against a screenshot.

    python -I fir_frame.py capture.fir [--frame N] [--shot screenshot.png --out overlay.png] [--matrices out.json] [--flip-scene] [--all]

For every draw: positions decoded (fir_geometry), the vertex shader evaluated symbolically (fir_xenos) to the draw's
object-to-clip transform, positions projected through the guest viewport registers. Reports how many draws get a
transform and why the rest don't. With --shot, draws the main-view wireframe over the screenshot (scaled to it).
"""
import json
import os
import struct
import sys
import zlib
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fir_read as fr  # noqa: E402
from fir_geometry import Converter, frame_regs_per_draw, load_shader_layouts  # noqa: E402
from fir_geometry import swap32, unpack  # noqa: E402
from fir_xenos import Fail  # noqa: E402
import fir_vs  # noqa: E402
import numpy as np  # noqa: E402


def make_fetch(cap, d, vidx):
    """A fetch function for fir_vs.run: the draw's vertex buffers, decoded per source vertex."""
    cache = {}

    def fetch(fld, idx):
        """idx: per-vertex fetch index (the vertex index for a plain fetch, a computed one for e.g. bone matrices)."""
        vb = next((b for b in d['bufs'] if b[0] == 1 and b[1] == fld['const']), None)
        if vb is None:
            return None
        data = cap.data.get((1, vb[6], vb[7]), {}).get('bytes', b'')
        ndw = len(data) // 4
        if not ndw:
            return None
        key = (vb[6], vb[7])
        if key not in cache:
            cache[key] = struct.unpack_from(f'<{ndw}I', data)
        words = cache[key]
        swap, stride, off, scale = vb[4], fld['stride'], fld['offset'], 2.0 ** fld['exp']
        out = np.zeros((len(idx), 4))
        for j, v in enumerate(idx):
            base = int(v) * stride + off
            w = [swap32(words[base + k], swap) if 0 <= base + k < ndw else 0 for k in range(4)]
            p = unpack(w, fld['format'], fld['signed'], fld['norm'])
            if p is None:
                return None
            out[j] = p
        return out * scale
    return fetch

VPORT = (0x210F, 0x2110, 0x2111, 0x2112, 0x2113, 0x2114)  # x scale, x offset, y scale, y offset, z scale, z offset
PA_CL_VTE_CNTL = 0x2206


def f32(u):
    return struct.unpack('<f', struct.pack('<I', u & 0xFFFFFFFF))[0]


def load_vs_code(path):
    code = {}
    with open(path, 'rb') as f:
        buf = f.read()
    pos = 0
    while pos + fr.PACKET.size <= len(buf):
        _, _, _, _, _, nrec, rbytes, bbytes = fr.PACKET.unpack_from(buf, pos)
        recs = buf[pos + fr.PACKET.size: pos + fr.PACKET.size + rbytes]
        blob = buf[pos + fr.PACKET.size + rbytes: pos + fr.PACKET.size + rbytes + bbytes]
        pos += fr.PACKET.size + rbytes + bbytes
        rp = 0
        for _ in range(nrec):
            rtype, _, rsize = fr.RECHDR.unpack_from(recs, rp)
            body = recs[rp:rp + rsize]
            rp += rsize
            if rtype == 0xF104:
                (h,) = struct.unpack_from('<Q', body, 8)
                (pixel,) = struct.unpack_from('<I', body, 16)
                off, size = fr.BLOB.unpack_from(body, 64)
                if not pixel:
                    code[h] = list(struct.unpack_from(f'<{size // 4}I', blob, off))
    return code


def read_png(path):
    with open(path, 'rb') as f:
        data = f.read()
    pos, w, h, idat, ctype = 8, 0, 0, b'', 0
    while pos < len(data):
        (n,) = struct.unpack('>I', data[pos:pos + 4])
        t = data[pos + 4:pos + 8]
        d = data[pos + 8:pos + 8 + n]
        if t == b'IHDR':
            w, h, depth, ctype = struct.unpack('>IIBB', d[:10])
        elif t == b'IDAT':
            idat += d
        pos += 12 + n
    bpp = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        ft = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ft == 1:
                line[x] = (line[x] + a) & 255
            elif ft == 2:
                line[x] = (line[x] + b) & 255
            elif ft == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        for x in range(w):
            o = (y * w + x) * 4
            out[o:o + 3] = line[x * bpp:x * bpp + 3]
            out[o + 3] = 255
    return w, h, out


def place(cap, path, code, frame, keep_atoms=False):
    """Runs every draw's vertex shader. Returns (draws, placed, why, kinds); placed: (draw, regs, geometry, clip per
    geometry vertex, matrix info[, atoms, vindex])."""
    regs_at = frame_regs_per_draw(cap, path, frame['index'])
    conv = Converter(cap)
    draws = cap.draws(frame)
    why = Counter()
    placed = []  # (draw, regs, geometry, clip per geometry vertex (None = rect corner), matrix info)
    kinds = Counter()
    for d, regs in zip(draws, regs_at):
        gid, reason = conv.convert_draw(d, regs)
        if not gid:
            why['geometry: ' + reason] += 1
            continue
        consts = {}
        for i in range(256 * 4):
            v = regs.get(0x4000 + i)
            if v is not None:
                consts[i] = f32(v)
        bools = {0x4900 + i: regs.get(0x4900 + i, 0) for i in range(8)}
        vidx = [v for v in conv.last_vindex if v is not None]
        if d['vs'] not in code:
            why['transform: shader code missing'] += 1
            continue
        try:
            rows, mach = fir_vs.run(code[d['vs']], consts, bools, make_fetch(cap, d, vidx), len(vidx), vertex_index=np.array(vidx, dtype=np.float64), loop_consts=
                                   {i: regs.get(0x4908 + i, 0) for i in range(32)})
        except Fail as e:
            why['transform: ' + str(e)] += 1
            continue
        clip = fir_vs.clip_positions(rows, len(vidx))
        per_vert, j = [], 0
        for v in conv.last_vindex:
            if v is None:
                per_vert.append(None)
            else:
                per_vert.append(clip[j])
                j += 1
        mi = fir_vs.matrix(rows)
        kind = 'no linear map' if mi is None else 'over the captured position' if all(k[0] == 'in' for k in mi[0]) else 'over computed values'
        kinds[kind] += 1
        placed.append((d, regs, conv.geometry[gid], per_vert, mi) + ((mach.atoms, list(conv.last_vindex), gid) if keep_atoms else ()))
    return draws, placed, why, kinds


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    cap = fr.Capture(path)
    load_shader_layouts(cap, path)
    code = load_vs_code(path)
    frame = cap.frames[0]
    if '--frame' in sys.argv:
        want = int(sys.argv[sys.argv.index('--frame') + 1])
        frame = next(f for f in cap.frames if f['index'] == want)
    draws, placed, why, kinds = place(cap, path, code, frame)
    n = len(draws)
    main_view = [p for p in placed if p[0]['flags'] & 4]
    print(f"frame {frame['index']}: {n} draws; clip positions for {len(placed)} ({100 * len(placed) / max(n, 1):.1f}%), "
          f"{len(main_view)} of them in the main view")
    for k, v in kinds.most_common():
        print(f'  last linear map {k}: {v}')
    for k, v in why.most_common():
        print(f'  {v} {k}')
    inside = total = 0
    for d, regs, g, pv, mi in main_view:
        for c in pv[:64]:
            if c is None:
                continue
            total += 1
            if c[3] > 1e-6 and abs(c[0] / c[3]) <= 1.2 and abs(c[1] / c[3]) <= 1.2:
                inside += 1
    print(f'main-view vertices (first 64 per draw) projecting into the view: {inside} of {total} ({100 * inside / max(total, 1):.1f}%)')
    if '--matrices' in sys.argv:
        out = sys.argv[sys.argv.index('--matrices') + 1]
        with open(out, 'w') as f:
            json.dump([{'seq': d['seq'], 'vs': f"{d['vs']:016x}", 'ps': f"{d['ps']:016x}", 'main_view': bool(d['flags'] & 4),
                        'atoms': [repr(a) for a in mi[0]] if mi else None, 'clip_from_atoms': mi[1] if mi else None}
                       for d, regs, g, pv, mi in placed], f)
        print(f'matrices written to {out}')
    if '--shot' in sys.argv:
        flip = '--flip-scene' in sys.argv
        # The scene pass is the longest stretch of draws without a resolve; its resolve ends it. Draws up to there go to
        # targets a later pass copies to the screen upside down; later passes (post, HUD) draw to the screen.
        rs = sorted(e[1]['seq'] for e in frame['events'] if e[0] == 'resolve')
        gaps = [(b - a, b) for a, b in zip([-1] + rs, rs)]
        last_resolve = max(gaps)[1] if gaps else -1
        sw, sh, img = read_png(sys.argv[sys.argv.index('--shot') + 1])
        drawn = 0
        chosen = main_view
        if '--all' in sys.argv:  # every placed draw drawn in the scene pass or after (not shadow or reflection passes)
            prev = max((r for r in rs if r < last_resolve), default=-1)
            chosen = [p for p in placed if p[0]['seq'] > prev]
        if '--seqs' in sys.argv:
            want = set(map(int, open(sys.argv[sys.argv.index('--seqs') + 1]).read().split()))
            chosen = [p for p in placed if p[0]['seq'] in want]
        for d, regs, g, pv, mi in chosen:
            xs, xo, ys, yo = (f32(regs.get(r, 0)) for r in VPORT[:4])
            # guest viewport -> screenshot: the guest renders at its own size; scale to the shot by the viewport extent
            gw, gh = abs(xs) * 2, abs(ys) * 2
            if gw < 1 or gh < 1:
                continue
            kx, ky = sw / gw, sh / gh
            pts = []
            for c in pv:
                if c is None or not np.all(np.isfinite(c)) or c[3] <= 1e-6:
                    pts.append(None)
                    continue
                sx = (c[0] / c[3] * xs + xo) * kx
                sy = (c[1] / c[3] * ys + yo) * ky
                if flip and d['seq'] < last_resolve:
                    # drawn into a target that a later pass copies to the screen rotated 180 deg (FM3)
                    sx, sy = sw - sx, sh - sy
                pts.append((sx, sy))
            for t in g['triangles'][:30000]:
                for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                    pa, pb = pts[a], pts[b]
                    if pa is None or pb is None:
                        continue
                    x0, y0, x1, y1 = int(pa[0]), int(pa[1]), int(pb[0]), int(pb[1])
                    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
                    if steps > 4000:
                        continue
                    for s in range(steps + 1):
                        px, py = x0 + (x1 - x0) * s // steps, y0 + (y1 - y0) * s // steps
                        if 0 <= px < sw and 0 <= py < sh:
                            o = (py * sw + px) * 4
                            img[o:o + 3] = b'\x00\xff\x60'
            drawn += 1
        fr.write_png(sys.argv[sys.argv.index('--out') + 1], sw, sh, bytes(img))
        print(f'overlay written ({drawn} draws)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
