#!/usr/bin/env python3
"""fir_geometry.py: stage-2 geometry conversion of a .fir capture (ReGPU fir_tap stage 1 records).

    python -I fir_geometry.py capture.fir [--frame N] [--obj DIR] [--max N] [--sheet out.png]

For each draw of a frame: the index buffer read and expanded to a triangle list (lists, strips with restart, fans,
quads, rect lists, as ReGPU's BuildIndexList does), the position attribute decoded from the vertex buffer with
ReGPU's fetch layout and Xenos format rules (hlsl.cpp Unpack/VFetchK, endian modes as Swap), in the shader's
object space (before the vertex shader). Geometry is deduplicated by geometry id (hash of positions and indices).

Reports how many draws convert and why the rest don't; optionally writes OBJ files and a wireframe contact sheet of
the largest meshes for a visual check. The position fetch is taken as the shader's first vertex fetch
(ReGPU's positionFetch rule).
"""
import hashlib
import math
import os
import struct
import sys
import zlib
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fir_read import Capture, write_png  # noqa: E402

PRIM_NAMES = {1: 'point list', 2: 'line list', 3: 'line strip', 4: 'triangle list', 5: 'triangle fan', 6: 'triangle strip', 8: 'rect list', 13: 'quad list'}
VGT_INDX_OFFSET, VGT_MULTI_PRIM_IB_RESET_INDX, PA_SU_SC_MODE_CNTL = 0x2102, 0x2103, 0x2205


def swap32(v, e):
    if e == 1:
        return ((v & 0x00FF00FF) << 8) | ((v >> 8) & 0x00FF00FF)
    if e == 2:
        return ((v >> 24) | ((v >> 8) & 0xFF00) | ((v << 8) & 0xFF0000) | (v << 24)) & 0xFFFFFFFF
    if e == 3:
        return ((v << 16) | (v >> 16)) & 0xFFFFFFFF
    return v


def xhalf(h):
    h &= 0xFFFF
    e, m = (h >> 10) & 31, h & 1023
    if e == 31:
        v = (1.0 + m / 1024.0) * 65536.0
    elif e == 0:
        v = m / 1024.0 * 2.0 ** -14
    else:
        v = (1.0 + m / 1024.0) * 2.0 ** (e - 15)
    return -v if h & 0x8000 else v


def sext(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def f32(w):
    return struct.unpack('<f', struct.pack('<I', w & 0xFFFFFFFF))[0]


def unpack(w, fmt, signed, norm):
    """ReGPU hlsl.cpp Unpack: w = four dwords (already endian-swapped)."""
    w0, w1, w2, w3 = w
    if fmt == 6:
        u = [w0 & 0xFF, (w0 >> 8) & 0xFF, (w0 >> 16) & 0xFF, w0 >> 24]
        if signed:
            r = [sext(x, 8) for x in u]
            return [max(x / 127.0, -1.0) for x in r] if norm else [float(x) for x in r]
        return [x / 255.0 for x in u] if norm else [float(x) for x in u]
    if fmt == 7:
        u = [w0 & 0x3FF, (w0 >> 10) & 0x3FF, (w0 >> 20) & 0x3FF, w0 >> 30]
        if signed:
            r = [sext(u[0], 10), sext(u[1], 10), sext(u[2], 10), sext(u[3], 2)]
            return [max(r[0] / 511, -1), max(r[1] / 511, -1), max(r[2] / 511, -1), max(r[3], -1)] if norm else [float(x) for x in r]
        return [u[0] / 1023, u[1] / 1023, u[2] / 1023, u[3] / 3] if norm else [float(x) for x in u]
    if fmt in (25, 26):
        u = [w0 & 0xFFFF, w0 >> 16, w1 & 0xFFFF, w1 >> 16]
        if signed:
            r = [sext(x, 16) for x in u]
            r = [max(x / 32767.0, -1.0) for x in r] if norm else [float(x) for x in r]
        else:
            r = [x / 65535.0 for x in u] if norm else [float(x) for x in u]
        return r[:2] + [0.0, 1.0] if fmt == 25 else r
    if fmt == 31:
        return [xhalf(w0), xhalf(w0 >> 16), 0.0, 1.0]
    if fmt == 32:
        return [xhalf(w0), xhalf(w0 >> 16), xhalf(w1), xhalf(w1 >> 16)]
    if fmt == 33:
        return [float(sext(w0, 32) if signed else w0), 0.0, 0.0, 1.0]
    if fmt == 34:
        return [float(sext(w0, 32) if signed else w0), float(sext(w1, 32) if signed else w1), 0.0, 1.0]
    if fmt == 35:
        return [float(sext(x, 32) if signed else x) for x in (w0, w1, w2, w3)]
    if fmt == 36:
        return [f32(w0), 0.0, 0.0, 1.0]
    if fmt == 37:
        return [f32(w0), f32(w1), 0.0, 1.0]
    if fmt == 57:
        return [f32(w0), f32(w1), f32(w2), 1.0]
    if fmt == 38:
        return [f32(w0), f32(w1), f32(w2), f32(w3)]
    if fmt in (16, 17):
        bits = (11, 11, 10) if fmt == 16 else (10, 11, 11)
        u = [w0 & ((1 << bits[0]) - 1), (w0 >> bits[0]) & ((1 << bits[1]) - 1), w0 >> (bits[0] + bits[1])]
        if signed:
            r = [sext(u[i], bits[i]) for i in range(3)]
            r = [max(r[i] / ((1 << (bits[i] - 1)) - 1), -1.0) for i in range(3)] if norm else [float(x) for x in r]
        else:
            r = [u[i] / ((1 << bits[i]) - 1) for i in range(3)] if norm else [float(x) for x in u]
        return r + [1.0]
    return None


def read_indices(data, count, is32, endian, offset, restart, reset):
    """ReGPU ReadIndex/BuildIndexList: raw indices + offset, and restart cut flags."""
    out, cut = [], []
    n = len(data) // (4 if is32 else 2)
    for i in range(count):
        if i >= n:
            out.append(offset)
            cut.append(False)
            continue
        if is32:
            (v,) = struct.unpack_from('<I', data, i * 4)
            v = swap32(v, endian) if endian in (1, 2) else v
            mask = 0xFFFFFF
        else:
            (v,) = struct.unpack_from('<H', data, i * 2)
            if endian in (1, 2):
                v = ((v & 0xFF) << 8) | (v >> 8)
            mask = 0xFFFF
        cut.append(restart and (v & mask) == reset)
        out.append(v + offset)
    return out, cut


def triangles(prim, g, cut):
    """Triangle list (triples of guest vertex indices) from a primitive's index list."""
    tris = []
    if prim == 4:
        for i in range(0, len(g) - 2, 3):
            tris.append((g[i], g[i + 1], g[i + 2]))
    elif prim in (5, 6):
        start, n = 0, len(g)
        while start < n:
            end = start
            while end < n and not cut[end]:
                end += 1
            for i in range(start, end - 2):
                k = i - start
                if prim == 5:
                    tris.append((g[start], g[i + 1], g[i + 2]))
                elif k & 1:
                    tris.append((g[i + 1], g[i], g[i + 2]))
                else:
                    tris.append((g[i], g[i + 1], g[i + 2]))
            start = end + 1
    elif prim == 13:
        for i in range(0, len(g) - 3, 4):
            tris += [(g[i], g[i + 1], g[i + 2]), (g[i], g[i + 2], g[i + 3])]
    elif prim == 8:  # rect list: three corners given, the fourth is v1 + v2 - v0 (made in positions below)
        for i in range(0, len(g) - 2, 3):
            tris.append((g[i], g[i + 1], g[i + 2], 'rect'))
    return tris


class Converter:
    def __init__(self, cap):
        self.cap = cap
        self.layouts = {}
        self.geometry = {}  # geometry id -> dict(positions, triangles)

    def convert_draw(self, d, regs):
        prim = d['prim']
        if prim not in (4, 5, 6, 8, 13):
            return None, f'primitive {PRIM_NAMES.get(prim, prim)}'
        shader = self.cap.shaders_full.get(d['vs'])
        if not shader or not shader['layouts']:
            return None, 'no vertex fetch layout (literal fetches)'
        lay = shader['layouts'][0]
        slot, fmt = lay[0] & 0x7F, (lay[0] >> 8) & 0x3F
        signed, norm, stride, off = bool(lay[0] & 0x4000), bool(lay[0] & 0x8000), lay[1], lay[2]
        exp = ((lay[3] << 10) & 0xFFFFFFFF)
        exp = (exp - (1 << 32) if exp & 0x80000000 else exp) >> 26
        vb = next((b for b in d['bufs'] if b[0] == 1 and b[1] == slot), None)
        if vb is None:
            return None, 'position buffer not captured'
        vdata = self.cap.data.get((1, vb[6], vb[7]), {}).get('bytes', b'')
        if not vdata:
            return None, 'position buffer empty'
        count = d['count']
        source = (d['initiator'] >> 6) & 3
        is32 = bool((d['initiator'] >> 11) & 1)
        offset = regs.get(VGT_INDX_OFFSET, 0)
        restart = bool((regs.get(PA_SU_SC_MODE_CNTL, 0) >> 21) & 1)
        reset = regs.get(VGT_MULTI_PRIM_IB_RESET_INDX, 0) & (0xFFFFFF if is32 else 0xFFFF)
        if source == 0:
            ib = next((b for b in d['bufs'] if b[0] == 0), None)
            idata = self.cap.data.get((0, ib[6], ib[7]), {}).get('bytes', b'') if ib else b''
            if not idata:
                return None, 'index buffer empty'
            g, cut = read_indices(idata, count, is32, ib[4], offset, restart, reset)
        elif source == 2:
            g, cut = [i + offset for i in range(count)], [False] * count
        else:
            return None, f'index source {source}'
        tris = triangles(prim, g, cut)
        if not tris:
            return None, 'no triangles'
        ndw = len(vdata) // 4
        swap = vb[4]
        cache = {}
        scale = 2.0 ** exp

        def pos(v):
            if v in cache:
                return cache[v]
            dwi = v * stride + off
            w = []
            for k in range(4):
                j = dwi + k
                if 0 <= j < ndw:
                    (x,) = struct.unpack_from('<I', vdata, j * 4)
                    w.append(swap32(x, swap))
                else:
                    w.append(0)
            p = unpack(w, fmt, signed, norm)
            r = None if p is None else (p[0] * scale, p[1] * scale, p[2] * scale, p[3] * scale)
            cache[v] = r
            return r

        out_tris, verts, remap, bad, vindex = [], [], {}, 0, []
        vcount = ndw // stride if stride else 0
        oob = 0
        for t in tris:
            ids = []
            ok = True
            if len(t) == 4:  # rect: a, b, c, and d = b + c - a
                a, b, c = (pos(t[0]), pos(t[1]), pos(t[2]))
                if None in (a, b, c):
                    bad += 1
                    continue
                dpt = tuple(b[i] + c[i] - a[i] for i in range(4))
                for p in (a, b, c, dpt):
                    remap_key = ('p',) + p
                    if remap_key not in remap:
                        remap[remap_key] = len(verts)
                        verts.append(p)
                        vindex.append(None)
                    ids.append(remap[remap_key])
                out_tris += [(ids[0], ids[1], ids[2]), (ids[2], ids[1], ids[3])]
                continue
            for v in t:
                if v >= vcount:
                    oob += 1
                p = pos(v)
                if p is None or any(map(lambda x: math.isnan(x) or math.isinf(x), p)):
                    ok = False
                    break
                if v not in remap:
                    remap[v] = len(verts)
                    verts.append(p)
                    vindex.append(v)
                ids.append(remap[v])
            if ok:
                out_tris.append(tuple(ids))
            else:
                bad += 1
        if not out_tris:
            return None, f'format {fmt} not decodable' if pos(tris[0][0]) is None else 'all triangles invalid'
        h = hashlib.blake2b(digest_size=16)
        for p in verts:
            h.update(struct.pack('<4f', *p))
        for t in out_tris:
            h.update(struct.pack('<3I', *t))
        gid = h.hexdigest()
        self.last_vindex = vindex  # this draw's source vertex index per geometry vertex (None: a rect's 4th corner)
        self.last_tris = out_tris
        if gid not in self.geometry:
            self.geometry[gid] = {'positions': verts, 'triangles': out_tris, 'draws': 0, 'format': fmt, 'prim': prim, 'oob': oob}
        self.geometry[gid]['draws'] += 1
        return gid, ('out of range indices' if oob else None)


def load_shader_layouts(cap, path):
    """Re-read the shader records for their fetch layouts (fir_read keeps only counts)."""
    cap.shaders_full = {}
    with open(path, 'rb') as f:
        buf = f.read()
    import fir_read as fr
    pos = 0
    while pos + fr.PACKET.size <= len(buf):
        magic, major, minor, seq, direction, nrec, rbytes, bbytes = fr.PACKET.unpack_from(buf, pos)
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
                pixel, = struct.unpack_from('<I', body, 16)
                nfc, nlay = struct.unpack_from('<II', body, 56)
                off, size = fr.BLOB.unpack_from(body, 96)
                lays = [struct.unpack_from('<4I', blob, off + i * 16) for i in range(nlay)]
                if not pixel:
                    cap.shaders_full[h] = {'layouts': lays}


def frame_regs_per_draw(cap, path, frame_no):
    """Register state at each draw of one frame (replays the deltas)."""
    import fir_read as fr
    with open(path, 'rb') as f:
        buf = f.read()
    pos, frame, regs, out = 0, None, {}, []
    while pos + fr.PACKET.size <= len(buf):
        magic, major, minor, seq, direction, nrec, rbytes, bbytes = fr.PACKET.unpack_from(buf, pos)
        recs = buf[pos + fr.PACKET.size: pos + fr.PACKET.size + rbytes]
        blob = buf[pos + fr.PACKET.size + rbytes: pos + fr.PACKET.size + rbytes + bbytes]
        pos += fr.PACKET.size + rbytes + bbytes
        rp = 0
        for _ in range(nrec):
            rtype, _, rsize = fr.RECHDR.unpack_from(recs, rp)
            body = recs[rp:rp + rsize]
            rp += rsize
            if rtype == 0x0010:
                (frame,) = struct.unpack_from('<Q', body, 8)
            if frame != frame_no:
                continue
            if rtype in (0xF101, 0xF102, 0xF103):
                if rtype == 0xF101:
                    count, _ = struct.unpack_from('<II', body, 8)
                    off, size = fr.BLOB.unpack_from(body, 16)
                else:
                    count, = struct.unpack_from('<I', body, 44 if rtype == 0xF102 else 12)
                    off, size = fr.BLOB.unpack_from(body, 48 if rtype == 0xF102 else 16)
                vals = struct.unpack_from(f'<{count * 2}I', blob, off) if count else ()
                for i in range(0, len(vals), 2):
                    regs[vals[i]] = vals[i + 1]
                if rtype == 0xF102:
                    out.append(dict(regs))
    return out


def wire_sheet(geoms, path, tile=256, cols=4):
    rows = (len(geoms) + cols - 1) // cols
    W, H = tile * cols, tile * max(rows, 1)
    img = bytearray(b'\x20\x20\x20\xff' * (W * H))

    def plot(x, y):
        if 0 <= x < W and 0 <= y < H:
            o = (y * W + x) * 4
            img[o:o + 4] = b'\xe0\xe0\xe0\xff'

    for n, g in enumerate(geoms):
        ox, oy = (n % cols) * tile, (n // cols) * tile
        ps = g['positions']
        # three-quarter view: rotate about Y by 35 deg, X by 25 deg, orthographic
        cy, sy, cx, sx = math.cos(0.6), math.sin(0.6), math.cos(0.45), math.sin(0.45)
        pr = []
        for x, y, z, _w in ps:
            x1, z1 = x * cy + z * sy, -x * sy + z * cy
            y1 = y * cx - z1 * sx
            pr.append((x1, y1))
        xs, ys = [p[0] for p in pr], [p[1] for p in pr]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
        s = (tile - 16) / span
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        sp = [(int(ox + tile / 2 + (x - mx) * s), int(oy + tile / 2 - (y - my) * s)) for x, y in pr]
        for t in g['triangles'][:20000]:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                (x0, y0), (x1, y1) = sp[a], sp[b]
                steps = max(abs(x1 - x0), abs(y1 - y0), 1)
                for k in range(steps + 1):
                    plot(x0 + (x1 - x0) * k // steps, y0 + (y1 - y0) * k // steps)
    write_png(path, W, H, bytes(img))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    cap = Capture(path)
    load_shader_layouts(cap, path)
    frame = cap.frames[0]
    if '--frame' in sys.argv:
        want = int(sys.argv[sys.argv.index('--frame') + 1])
        frame = next(f for f in cap.frames if f['index'] == want)
    regs_at = frame_regs_per_draw(cap, path, frame['index'])
    conv = Converter(cap)
    reasons = Counter()
    ok = 0
    oob_draws = 0
    draws = cap.draws(frame)
    for d, regs in zip(draws, regs_at):
        gid, why = conv.convert_draw(d, regs)
        if gid:
            ok += 1
            if why:
                oob_draws += 1
        else:
            reasons[why] += 1
    print(f"frame {frame['index']}: {len(draws)} draws, {ok} converted ({100 * ok / max(len(draws), 1):.1f}%), "
          f"{len(conv.geometry)} distinct geometries; {oob_draws} converted draws had indices past the buffer")
    for why, n in reasons.most_common():
        print(f'  not converted: {n} {why}')
    fmts = Counter(g['format'] for g in conv.geometry.values())
    print('position formats: ' + ', '.join(f'{k}: {v}' for k, v in fmts.most_common()))
    tris = sum(len(g['triangles']) for g in conv.geometry.values())
    print(f'triangles in distinct geometry: {tris}')
    big = sorted(conv.geometry.values(), key=lambda g: len(g['triangles']), reverse=True)
    n = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 12
    if '--sheet' in sys.argv:
        wire_sheet(big[:n], sys.argv[sys.argv.index('--sheet') + 1])
        print('wireframe sheet written')
    if '--obj' in sys.argv:
        out = sys.argv[sys.argv.index('--obj') + 1]
        os.makedirs(out, exist_ok=True)
        for i, g in enumerate(big[:n]):
            with open(os.path.join(out, f'mesh{i:03d}.obj'), 'w') as f:
                for p in g['positions']:
                    f.write('v %g %g %g\n' % p[:3])
                for t in g['triangles']:
                    f.write('f %d %d %d\n' % (t[0] + 1, t[1] + 1, t[2] + 1))
        print(f'{min(n, len(big))} OBJ files written to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
