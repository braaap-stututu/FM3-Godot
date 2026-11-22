"""fm3_pvs.py: FM3 track placement/visibility files (Media/Tracks/<track>/Ribbon_NN/<track>_NN.pvs), magic FPVS v24.

Worked out on Ladera (CrownJewel) with FM4's v27 reader (FH1-ReImagined tools/fm4_pvs.py) as the guide. Big-endian.
  header: 'FPVS', u32 version (24), u32 ?, u16 ribbon (layout number), u16 ?, then u32 cell count and cells (u16 lists,
          not decoded here),
  texture table (found by its record-0 pattern): u32 count, records of 28 bytes:
          u32 texture file id (_0x<id>.bix), u32 index (sequential), f32 scale x, scale y, offset x, offset y (an atlas
          rectangle; 1, 1, 0, 0 for a whole texture), u32 flags
  shader names: u32 count, strings (u32 length + 'shaders\\track\\...')
  instances: u32 count, records of 56 bytes:
          u16 model, u32 flags, u32 lightmap (texture table index), u32, u32, u16, u16[3] LOD distances (half),
          f32[3] position, u16[9] rotation 3x3 (half floats, row-major)
  models: u32 count, records: u32 n + u32[n] texture table indices, u32 m + u32[m] shader indices, f32[16] matrix,
          f32[4] extent. Model i is the track's <prefix>out.<i:05d>.rmb.bin.
"""
import struct

import numpy as np


def _half(u16s):
    return np.frombuffer(struct.pack('>%dH' % len(u16s), *u16s), dtype='>f2').astype(np.float64)


def parse(data):
    b = data
    if b[:4] != b'FPVS':
        raise ValueError('not an FPVS file')
    out = {'version': struct.unpack_from('>I', b, 4)[0], 'ribbon': struct.unpack_from('>H', b, 12)[0]}
    # texture table: record 0 = (id, 0, 1.0, 1.0, 0, 0, flag), record 1 index 1, ...
    tex_at = None
    one = struct.pack('>ff', 1.0, 1.0)
    p = b.find(one)
    while p >= 0:
        q = p - 8
        if q >= 4 and struct.unpack_from('>I', b, q + 4)[0] == 0 and struct.unpack_from('>I', b, q + 28 + 4)[0] == 1 \
                and struct.unpack_from('>I', b, q + 56 + 4)[0] == 2:
            tex_at = q
            break
        p = b.find(one, p + 1)
    if tex_at is None:
        raise ValueError('texture table not found')
    n = struct.unpack_from('>I', b, tex_at - 4)[0]
    tex = []
    for i in range(n):
        tid, idx, sx, sy, ox, oy, flags = struct.unpack_from('>II4fI', b, tex_at + 28 * i)
        tex.append({'id': tid, 'rect': (sx, sy, ox, oy), 'flags': flags})
    out['textures'] = tex
    o = tex_at + 28 * n
    ns = struct.unpack_from('>I', b, o)[0]
    o += 4
    shaders = []
    for _ in range(ns):
        L = struct.unpack_from('>I', b, o)[0]
        shaders.append(b[o + 4:o + 4 + L].decode('latin-1'))
        o += 4 + L
    out['shaders'] = shaders
    ni = struct.unpack_from('>I', b, o)[0]
    o += 4
    inst = []
    for i in range(ni):
        r = b[o + 56 * i:o + 56 * (i + 1)]
        model, flags, lm, u1, u2, u3 = struct.unpack_from('>HIIIIH', r, 0)
        lod = _half(struct.unpack_from('>3H', r, 20))
        pos = struct.unpack_from('>3f', r, 26)
        rot = _half(struct.unpack_from('>9H', r, 38)).reshape(3, 3)
        inst.append({'model': model, 'flags': flags, 'lightmap': lm, 'lod': lod.tolist(), 'pos': pos, 'rot': rot})
    out['instances'] = inst
    o += 56 * ni
    nm = struct.unpack_from('>I', b, o)[0]
    o += 4
    models = []
    for _ in range(nm):
        nt = struct.unpack_from('>I', b, o)[0]
        t = list(struct.unpack_from('>%dI' % nt, b, o + 4))
        o += 4 + 4 * nt
        nsh = struct.unpack_from('>I', b, o)[0]
        s = list(struct.unpack_from('>%dI' % nsh, b, o + 4))
        o += 4 + 4 * nsh
        M = np.array(struct.unpack_from('>16f', b, o)).reshape(4, 4)
        o += 64
        ext = struct.unpack_from('>4f', b, o)
        o += 16
        models.append({'textures': t, 'shaders': s, 'matrix': M, 'extent': ext})
    out['models'] = models
    out['end'] = o
    return out
