"""fm3_track.py: FM3 track model files (.rmb.bin, from Media/Tracks/<track>/bin.zip, extracted with tools/fm3unzip).

Layout (big-endian), worked out from AmalfiGP against captured draws (index lists verbatim):
  u32 ?, f32[4] bbox min, f32[4] bbox max, f32[16] matrix,
  u32 a, u32 b, u32 0, u32 1, u32 1, u32 1, f32[4] centre?, f32[4] min, f32[4] max, u32 mesh count?,
  then per mesh section:
    u32 name length, name (e.g. BARR_JersyBarrier_LOD00_001), u32 ?, u32 vertex count, u32 stride (24),
    vertex count * stride bytes: f32[3] model-space position + 12 packed bytes (as the GPU buffer, which has the
    position in world space),
    u32 1, u32 1, u32 1, u32 2?, u32 material name length, material name, parameters, u32 prim (3 = strip),
    u32 index count, u32 index size (2), indices (u16, 0xFFFF = restart).

parse(data) -> {'name', 'meshes': [{'name', 'stride', 'positions' (n, 3), 'raw' vertex bytes, 'material',
'prim', 'indices'}]} — tolerant: it scans for the vertex block header after the model name.
"""
import re
import struct

import numpy as np

_NAME = re.compile(rb'\x00\x00\x00([\x04-\x7f])([A-Za-z0-9_\-\.]{4,127})')


def _find_names(data, start=0):
    out = []
    for m in _NAME.finditer(data, start):
        if m.group(1)[0] == len(m.group(2)):
            out.append((m.start(), m.group(2).decode()))
    return out


def parse(data):
    model = {'meshes': []}
    names = _find_names(data)
    i = 0
    while i < len(names):
        off, nm = names[i]
        p = off + 4 + len(nm)
        # vertex block: u32 ?, u32 count, u32 stride (12..64)
        if p + 12 <= len(data):
            _, cnt, stride = struct.unpack_from('>III', data, p)
            if 0 < cnt < 200000 and stride in (16, 20, 24, 28, 32, 36, 40, 44, 48) and p + 12 + cnt * stride <= len(data):
                vstart = p + 12
                raw = data[vstart:vstart + cnt * stride]
                pos = np.frombuffer(raw, dtype='>f4').reshape(cnt, stride // 4)[:, :3].astype(np.float64)
                mesh = {'name': nm, 'stride': stride, 'positions': pos, 'raw': raw, 'material': None, 'prim': None, 'indices': None}
                # material and index list follow
                after = vstart + cnt * stride
                mat = next(((o, n) for o, n in names if o >= after), None)
                if mat is not None:
                    mesh['material'] = mat[1]
                    q = mat[0] + 4 + len(mat[1])
                    # scan forward for (prim, count, size) with size 2 or 4 and a sane count
                    for k in range(q, min(q + 400, len(data) - 12), 4):
                        prim, icount, isize = struct.unpack_from('>III', data, k)
                        if prim in (1, 2, 3, 4, 5, 6) and isize in (2, 4) and 3 <= icount < 2000000 and k + 12 + icount * isize <= len(data):
                            fmt = '>u2' if isize == 2 else '>u4'
                            idx = np.frombuffer(data, dtype=fmt, count=icount, offset=k + 12).astype(np.int64)
                            valid = idx[(idx != 0xFFFF) & (idx != 0xFFFFFFFF)]
                            if len(valid) and valid.max() < cnt:
                                mesh['prim'], mesh['indices'], mesh['index_offset'] = prim, idx, k + 12
                                break
                model['meshes'].append(mesh)
                # continue after this mesh's index list
                end = mesh.get('index_offset', after) + (len(mesh['indices']) * (2 if mesh['prim'] else 0) if mesh['indices'] is not None else 0)
                while i < len(names) and names[i][0] < end:
                    i += 1
                continue
        if 'name' not in model:
            model['name'] = nm
        i += 1
    return model


def strip_to_triangles(idx, restart=0xFFFF):
    tris, run = [], []
    for v in list(idx) + [restart]:
        if v == restart:
            for k in range(len(run) - 2):
                a, b, c = run[k], run[k + 1], run[k + 2]
                if a != b and b != c and a != c:
                    tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
            run = []
        else:
            run.append(int(v))
    return tris
